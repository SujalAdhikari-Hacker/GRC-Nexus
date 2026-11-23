"""Tests for the NIS2 Article 23 incident clock and deadline sweep."""
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Department, User
from core.notifications import Notification

from .forms import IncidentForm
from .models import Incident, Nis2DeadlineAlert
from .nis2 import (
    EARLY_WARNING_HOURS,
    FINAL_REPORT_DAYS,
    NOTIFICATION_HOURS,
    compute_deadlines,
    derive_phase,
    phase_clocks,
)
from .services import sweep_deadlines

DETECTED = datetime(2026, 3, 1, 12, 0, tzinfo=dt_timezone.utc)


def clocks_at(now, submitted=None):
    return {c.phase: c for c in phase_clocks(DETECTED, submitted, now)}


class Nis2ClockTests(SimpleTestCase):
    def test_deadlines_are_24h_72h_and_30_days_after_detection(self):
        deadlines = compute_deadlines(DETECTED)
        self.assertEqual(
            deadlines['early_warning'],
            DETECTED + timedelta(hours=EARLY_WARNING_HOURS),
        )
        self.assertEqual(
            deadlines['notification'],
            DETECTED + timedelta(hours=NOTIFICATION_HOURS),
        )
        self.assertEqual(
            deadlines['final_report'],
            DETECTED + timedelta(days=FINAL_REPORT_DAYS),
        )
        self.assertEqual(EARLY_WARNING_HOURS, 24)
        self.assertEqual(NOTIFICATION_HOURS, 72)
        self.assertEqual(FINAL_REPORT_DAYS, 30)

    def test_pending_until_two_hours_before_the_deadline(self):
        clocks = clocks_at(DETECTED + timedelta(hours=1))
        self.assertEqual(clocks['early_warning'].state, 'pending')
        self.assertEqual(clocks['notification'].state, 'pending')
        self.assertEqual(clocks['final_report'].state, 'pending')

    def test_due_soon_inside_the_two_hour_window(self):
        clocks = clocks_at(DETECTED + timedelta(hours=22))
        self.assertEqual(clocks['early_warning'].state, 'due_soon')
        self.assertEqual(clocks['early_warning'].remaining_label, '2h 0m left')
        self.assertEqual(clocks['notification'].state, 'pending')

    def test_breached_once_the_deadline_passes(self):
        clocks = clocks_at(DETECTED + timedelta(hours=25))
        self.assertEqual(clocks['early_warning'].state, 'breached')
        self.assertIn('overdue', clocks['early_warning'].remaining_label)
        self.assertEqual(clocks['notification'].state, 'pending')

    def test_submission_overrides_breach_and_records_lateness(self):
        clocks = clocks_at(
            DETECTED + timedelta(hours=30),
            {'early_warning': DETECTED + timedelta(hours=25)},
        )
        early = clocks['early_warning']
        self.assertEqual(early.state, 'submitted')
        self.assertTrue(early.submitted_late)

    def test_on_time_submission_is_not_late(self):
        clocks = clocks_at(
            DETECTED + timedelta(hours=2),
            {'early_warning': DETECTED + timedelta(hours=2)},
        )
        self.assertFalse(clocks['early_warning'].submitted_late)

    def test_phase_advances_in_statutory_order(self):
        self.assertEqual(derive_phase(), 'early_warning')
        self.assertEqual(
            derive_phase({'early_warning': DETECTED}), 'notification'
        )
        self.assertEqual(
            derive_phase({
                'early_warning': DETECTED, 'notification': DETECTED,
            }),
            'final_report',
        )
        self.assertEqual(
            derive_phase({
                'early_warning': DETECTED,
                'notification': DETECTED,
                'final_report': DETECTED,
            }),
            'complete',
        )


class Nis2Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='NIS2 Dept')
        cls.user = User.objects.create_user(
            'nis2_user', 'nis2@example.com', 'pw', department=cls.dept,
        )
        cls.handler = User.objects.create_user(
            'nis2_handler', 'nis2h@example.com', 'pw', department=cls.dept,
        )

    def make_incident(self, hours_ago=0, **kwargs):
        defaults = dict(
            title='Ransomware on file server',
            description='File server encrypted; backups verified.',
            incident_type='ransomware',
            severity='high',
            owner_dept=self.dept,
            detected_at=timezone.now() - timedelta(hours=hours_ago),
            nis2_significant=True,
        )
        defaults.update(kwargs)
        return Incident.objects.create(**defaults)

    def alerts(self, incident):
        return Nis2DeadlineAlert.objects.filter(incident=incident)

    def notifications(self, incident, kind):
        return Notification.objects.filter(
            kind=kind,
            ref_model='incidents.Incident',
            ref_id=incident.pk,
        )


class Nis2SweepTests(Nis2Base):
    def test_pre_deadline_alert_fires_once_then_dedupes(self):
        now = timezone.now()
        incident = self.make_incident(hours_ago=23)  # 1 h left on the 24 h clock

        first = sweep_deadlines(now=now)
        self.assertEqual(len(first['dispatched']), 1)
        self.assertEqual(first['dispatched'][0]['kind'], 'pre_deadline')
        self.assertEqual(
            self.alerts(incident).filter(
                phase='early_warning', kind='pre_deadline').count(),
            1,
        )
        self.assertEqual(
            self.notifications(incident, 'incident_nis2_due').count(), 1
        )

        second = sweep_deadlines(now=now)
        self.assertEqual(second['dispatched'], [])
        self.assertEqual(self.alerts(incident).count(), 1)
        self.assertEqual(
            self.notifications(incident, 'incident_nis2_due').count(), 1
        )

    def test_breach_alert_and_notification(self):
        now = timezone.now()
        incident = self.make_incident(hours_ago=25)

        result = sweep_deadlines(now=now)

        self.assertEqual(result['dispatched'][0]['kind'], 'breach')
        self.assertEqual(
            self.alerts(incident).filter(phase='early_warning', kind='breach').count(),
            1,
        )
        self.assertEqual(
            self.notifications(incident, 'incident_nis2_breach').count(), 1
        )

    def test_alert_targets_handler_and_department(self):
        now = timezone.now()
        incident = self.make_incident(hours_ago=25, handler=self.handler)

        sweep_deadlines(now=now)

        notification = self.notifications(incident, 'incident_nis2_breach').get()
        self.assertEqual(notification.owner_dept, self.dept)
        self.assertEqual(notification.recipient, self.handler)

    def test_submitted_phase_is_not_alerted(self):
        incident = self.make_incident(hours_ago=25)
        incident.nis2_early_warning_submitted_at = incident.detected_at + timedelta(
            hours=1
        )
        incident.save()

        result = sweep_deadlines(now=timezone.now())

        self.assertEqual(result['dispatched'], [])

    def test_non_significant_incident_is_ignored(self):
        now = timezone.now()
        self.make_incident(hours_ago=48, nis2_significant=False)

        result = sweep_deadlines(now=now)

        self.assertEqual(result['dispatched'], [])
        self.assertEqual(Nis2DeadlineAlert.objects.count(), 0)

    def test_closed_incident_is_ignored(self):
        now = timezone.now()
        self.make_incident(hours_ago=48, status='closed')

        result = sweep_deadlines(now=now)

        self.assertEqual(result['dispatched'], [])

    def test_dry_run_writes_nothing(self):
        now = timezone.now()
        incident = self.make_incident(hours_ago=25)

        result = sweep_deadlines(now=now, dry_run=True)

        self.assertEqual(len(result['dispatched']), 1)
        self.assertEqual(self.alerts(incident).count(), 0)
        self.assertEqual(
            self.notifications(incident, 'incident_nis2_breach').count(), 0
        )

    def test_management_command_runs(self):
        self.make_incident(hours_ago=25)
        call_command('sweep_nis2_deadlines', '--dry-run', stdout=StringIO())


class Nis2DetailTests(Nis2Base):
    def setUp(self):
        self.client.force_login(self.user)

    def test_detail_renders_the_clock(self):
        incident = self.make_incident(hours_ago=23)
        response = self.client.get(
            reverse('incidents:detail', kwargs={'pk': incident.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NIS2 Article 23 clock')
        self.assertContains(response, 'Early warning (24 h)')
        self.assertContains(response, 'Due soon')

    def test_detail_omits_clock_when_not_significant(self):
        incident = self.make_incident(hours_ago=23, nis2_significant=False)
        response = self.client.get(
            reverse('incidents:detail', kwargs={'pk': incident.pk})
        )
        self.assertNotContains(response, 'NIS2 Article 23 clock')

    def test_detail_shows_a_breach_banner(self):
        incident = self.make_incident(hours_ago=25)
        response = self.client.get(
            reverse('incidents:detail', kwargs={'pk': incident.pk})
        )
        self.assertContains(response, 'overdue')


class Nis2FormTests(Nis2Base):
    def test_form_records_the_significance_flag_and_submission(self):
        form = IncidentForm(data={
            'title': 'Significant outage',
            'description': 'Payment API unavailable for two hours.',
            'incident_type': 'ddos',
            'source': 'monitoring',
            'severity': 'high',
            'status': 'detected',
            'detected_at': '2026-03-01T12:00',
            'nis2_significant': 'on',
            'nis2_early_warning_submitted_at': '2026-03-01T18:00',
            'data_subjects_affected': '0',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.owner_dept = self.dept
        incident = form.save()
        self.assertTrue(incident.nis2_significant)
        self.assertIsNotNone(incident.nis2_early_warning_submitted_at)
        self.assertEqual(incident.nis2_phase, 'notification')

    def test_report_cannot_precede_detection(self):
        form = IncidentForm(data={
            'title': 'Backdated report',
            'description': 'Report timestamped before awareness.',
            'incident_type': 'other',
            'source': 'employee',
            'severity': 'medium',
            'status': 'detected',
            'detected_at': '2026-03-01T12:00',
            'nis2_significant': 'on',
            'nis2_early_warning_submitted_at': '2026-02-28T12:00',
            'data_subjects_affected': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('nis2_early_warning_submitted_at', form.errors)
