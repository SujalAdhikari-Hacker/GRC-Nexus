"""Tests for the incident register, its notifications and escalations."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.escalations import collect_escalations
from core.models import Department, User
from core.notifications import Notification
from risks.models import Risk

from .models import TRIAGE_SLA_HOURS, Incident


class IncidentBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Incident Dept')
        cls.other = Department.objects.create(name='Other Dept')
        cls.user = User.objects.create_user(
            'handler', 'handler@example.com', 'pw', department=cls.dept,
        )
        cls.hod = User.objects.create_user(
            'inc_hod', 'hod@example.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.superuser = User.objects.create_superuser('inc_su', 'su@example.com', 'pw')

    def make_incident(self, **kwargs):
        defaults = dict(
            title='Stolen laptop', description='Laptop taken from a car.',
            incident_type='lost_device', severity='low',
            owner_dept=self.dept, detected_at=timezone.now(),
        )
        defaults.update(kwargs)
        return Incident.objects.create(**defaults)


class IncidentBasicsTests(IncidentBase):
    def test_reference_is_monotonic(self):
        first = self.make_incident()
        second = self.make_incident()
        self.assertTrue(first.reference.startswith('INC-'))
        self.assertNotEqual(first.reference, second.reference)
        self.assertEqual(int(second.reference.rsplit('-', 1)[1]),
                         int(first.reference.rsplit('-', 1)[1]) + 1)

    def test_lifecycle_stamps_track_status(self):
        incident = self.make_incident()
        self.assertIsNone(incident.triaged_at)
        incident.status = 'triaged'
        incident.save()
        incident.refresh_from_db()
        self.assertIsNotNone(incident.triaged_at)
        # Moving backwards clears the stamp again.
        incident.status = 'detected'
        incident.save()
        incident.refresh_from_db()
        self.assertIsNone(incident.triaged_at)

    def test_closing_requires_root_cause(self):
        incident = self.make_incident()
        incident.status = 'closed'
        incident.save()
        incident.refresh_from_db()
        # Model stamps closed_at; clean() must refuse a close without root cause.
        self.assertIsNotNone(incident.closed_at)
        incident.root_cause = ''
        self.assertRaises(Exception, incident.full_clean)

    def test_badge_classes_use_bootstrap_palette(self):
        incident = self.make_incident(severity='critical')
        self.assertEqual(incident.severity_badge, 'bg-danger')
        self.assertEqual(incident.status_badge, 'bg-warning')

    def test_status_flow_moves_forward_only(self):
        from .forms import IncidentForm
        incident = self.make_incident(status='triaged')
        allowed = [v for v, _ in IncidentForm(instance=incident).fields['status'].choices]
        self.assertEqual(
            allowed, ['triaged', 'contained', 'mitigated', 'closed'])
        # An unsaved report can only claim detection or initial triage.
        allowed = [v for v, _ in IncidentForm().fields['status'].choices]
        self.assertEqual(allowed, ['detected', 'triaged'])


class IncidentNotificationTests(IncidentBase):
    def test_new_incident_raises_department_notification(self):
        self.make_incident()
        n = Notification.objects.filter(
            kind='incident_open', owner_dept=self.dept, is_cleared=False,
        )
        self.assertTrue(n.exists())

    def test_notification_clears_when_incident_is_closed(self):
        incident = self.make_incident()
        incident.status = 'closed'
        incident.save()
        from core.notification_registry import refresh_notifications_throttled
        cleared = refresh_notifications_throttled(
            dept=self.dept, is_super=False, force=True)
        self.assertGreaterEqual(cleared, 1)
        self.assertFalse(Notification.objects.filter(
            kind='incident_open', owner_dept=self.dept, is_cleared=False,
        ).exists())


class IncidentAuthTests(IncidentBase):
    def test_other_department_incident_not_editable(self):
        other_incident = self.make_incident(owner_dept=self.other)
        self.client.force_login(self.user)
        resp = self.client.get(f'/incidents/{other_incident.pk}/edit/')
        self.assertEqual(resp.status_code, 404)

    def test_own_department_editable(self):
        incident = self.make_incident()
        self.client.force_login(self.user)
        resp = self.client.get(f'/incidents/{incident.pk}/edit/')
        self.assertEqual(resp.status_code, 200)

    def test_list_is_department_scoped(self):
        self.make_incident(owner_dept=self.dept)
        self.make_incident(owner_dept=self.other, title='Other team incident')
        self.client.force_login(self.hod)
        resp = self.client.get('/incidents/')
        self.assertContains(resp, 'Stolen laptop')
        self.assertNotContains(resp, 'Other team incident')

    def test_superuser_sees_all(self):
        self.make_incident(owner_dept=self.other)
        self.client.force_login(self.superuser)
        resp = self.client.get('/incidents/')
        self.assertEqual(200, resp.status_code)

    def test_csv_export(self):
        self.make_incident()
        self.client.force_login(self.hod)
        resp = self.client.get('/incidents/?export=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        text = resp.content.decode('utf-8-sig')
        self.assertIn('Stolen laptop', text)


class IncidentCloseAndRiskTests(IncidentBase):
    def test_close_view_requires_root_cause(self):
        incident = self.make_incident()
        self.client.force_login(self.user)
        resp = self.client.post(f'/incidents/{incident.pk}/close/', {
            'root_cause': 'Laptop left unattended overnight.',
            'lessons_learned': 'Safe storage policy now applies.',
        })
        incident.refresh_from_db()
        self.assertEqual(incident.status, 'closed')
        self.assertRedirects(resp, f'/incidents/{incident.pk}/')

    def test_close_get_shows_confirmation(self):
        incident = self.make_incident()
        self.client.force_login(self.user)
        resp = self.client.get(f'/incidents/{incident.pk}/close/')
        self.assertContains(resp, 'Closing is final')

    def test_closed_incident_cannot_be_closed_again(self):
        incident = self.make_incident(status='closed')
        self.client.force_login(self.user)
        resp = self.client.get(f'/incidents/{incident.pk}/close/')
        self.assertEqual(resp.status_code, 404)

    def test_raise_risk_creates_and_links(self):
        incident = self.make_incident(severity='high')
        self.client.force_login(self.user)
        resp = self.client.post(f'/incidents/{incident.pk}/raise-risk/')
        risk = Risk.objects.filter(title__icontains=incident.reference).first()
        self.assertIsNotNone(risk)
        self.assertEqual(risk.owner_dept, self.dept)
        self.assertIn(risk, incident.risks.all())
        self.assertEqual(risk.impact, 4)
        self.assertRedirects(resp, reverse('risks:detail', args=[risk.pk]))

    def test_second_open_risk_refused(self):
        from risks.models import RiskCategory
        incident = self.make_incident(severity='high')
        self.client.force_login(self.user)
        category, _ = RiskCategory.objects.get_or_create(name='Security incident')
        risk = Risk.objects.create(
            title='Existing linked risk', category=category,
            owner_dept=self.dept,
        )
        incident.risks.add(risk)
        self.client.post(f'/incidents/{incident.pk}/raise-risk/')
        self.assertEqual(Risk.objects.filter(
            title__icontains=incident.reference).count(), 0)

    def test_raise_risk_is_post_only(self):
        incident = self.make_incident()
        self.client.force_login(self.user)
        resp = self.client.get(f'/incidents/{incident.pk}/raise-risk/')
        self.assertEqual(resp.status_code, 200)


class IncidentEscalationTests(IncidentBase):
    def test_untriaged_critical_incident_escalates(self):
        waited = TRIAGE_SLA_HOURS['critical'] + 2
        incident = self.make_incident(
            severity='critical', status='detected',
            detected_at=timezone.now() - timedelta(hours=waited),
        )
        escalations = collect_escalations()
        kinds = [e.kind for e in escalations]
        self.assertIn('incident_sla_breach', kinds)
        sla = [e for e in escalations if e.kind == 'incident_sla_breach'
               and e.ref == incident]
        self.assertTrue(sla)
        self.assertEqual(sla[0].flag, 'email_on_incident')
        self.assertIn('not been triaged', sla[0].title)

    def test_triaged_incident_does_not_escalate(self):
        waited = TRIAGE_SLA_HOURS['critical'] + 2
        self.make_incident(
            severity='critical', status='triaged',
            detected_at=timezone.now() - timedelta(hours=waited),
        )
        escalations = collect_escalations()
        self.assertNotIn('incident_sla_breach', [e.kind for e in escalations])

    def test_breach_clock_overdue_escalates(self):
        incident = self.make_incident(
            incident_type='data_breach', severity='high',
            regulatory_notification_required=True,
            detected_at=timezone.now() - timedelta(hours=100),
        )
        escalations = collect_escalations()
        breach = [e for e in escalations
                  if e.kind == 'incident_breach_due' and e.ref == incident]
        self.assertTrue(breach)
        self.assertEqual(breach[0].severity, 'danger')
        self.assertIn('overdue', breach[0].title)

    def test_notified_breach_does_not_escalate(self):
        self.make_incident(
            incident_type='data_breach', severity='high',
            regulatory_notification_required=True,
            regulatory_notified_at=timezone.now(),
            detected_at=timezone.now() - timedelta(hours=100),
        )
        escalations = collect_escalations()
        self.assertNotIn(
            'incident_breach_due', [e.kind for e in escalations])

    def test_non_breach_incident_never_on_breach_clock(self):
        self.make_incident(incident_type='lost_device')
        escalations = collect_escalations()
        self.assertNotIn(
            'incident_breach_due', [e.kind for e in escalations])


class IncidentDashboardTests(IncidentBase):
    def test_dashboard_renders_incident_widget(self):
        self.make_incident(severity='high')
        self.client.force_login(self.superuser)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Open Incidents')
        self.assertContains(resp, 'Stolen laptop')


class IncidentSuperadminAndClosureTests(IncidentBase):
    def test_departmentless_superuser_can_file_incident(self):
        self.assertIsNone(self.superuser.department_id)
        self.client.force_login(self.superuser)
        resp = self.client.post(reverse('incidents:create'), {
            'title': 'Superadmin reported incident',
            'description': 'Suspicious outbound traffic observed.',
            'incident_type': 'unauthorized_access',
            'source': 'monitoring',
            'severity': 'high',
            'status': 'detected',
            'detected_at': '2026-11-28T09:00',
            'data_subjects_affected': 0,
            'owner_dept': self.dept.pk,
        })
        self.assertRedirects(resp, reverse('incidents:list'))
        inc = Incident.objects.get(title='Superadmin reported incident')
        self.assertEqual(inc.owner_dept, self.dept)

    def test_edit_to_closed_requires_root_cause(self):
        incident = self.make_incident()
        self.client.force_login(self.user)
        resp = self.client.post(reverse('incidents:update', args=[incident.pk]), {
            'title': incident.title,
            'description': incident.description,
            'incident_type': incident.incident_type,
            'source': incident.source,
            'severity': incident.severity,
            'status': 'closed',
            'detected_at': '2026-11-28T09:00',
            'data_subjects_affected': 0,
            'root_cause': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(
            resp.context['form'],
            'root_cause',
            'An incident cannot be closed without a root cause.',
        )
        incident.refresh_from_db()
        self.assertNotEqual(incident.status, 'closed')
