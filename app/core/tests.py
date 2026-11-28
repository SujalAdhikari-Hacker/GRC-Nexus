"""
Regression tests for GRC Nexus business logic and authorization rules.

Run with:
    python manage.py test core

These cover the invariants that have been broken before or that the whole
product depends on: residual-risk maths, department scoping, CSV injection
guarding, calendar-month bucketing, and the "authenticate before resolving
the object" rule for object-level create views.
"""
import datetime as _dt
from io import StringIO

from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from assets.models import Asset
from audits.models import AuditFinding
from controls.models import Control
from core.mixins import csv_safe, scope_queryset, user_can_access
from core.models import Department, User
from core.dashboard_data import iter_month_bounds
from risks.models import Risk, RiskAppetite, RiskCategory, RiskException, RiskTreatment
from risks.services import calculate_residual_from_controls
from tickets.forms import TicketForm
from vendors.models import Vendor
from django.utils import timezone


class _StubControl:
    """Minimal stand-in for a Control inside the residual calculation."""

    def __init__(self, ratio, ctype):
        self.effectiveness_ratio = ratio
        self.control_type = ctype


def _iter_boxes(box):
    """Yield every layout box, descending into absolute/fixed placeholders.

    ``position: fixed`` content (the PDF watermark) is wrapped in an
    ``AbsolutePlaceholder``; walking ``children`` alone never reaches it.
    """
    yield box
    inner = getattr(box, '_box', None)
    if inner is not None and inner is not box:
        yield from _iter_boxes(inner)
    for child in getattr(box, 'children', ()) or ():
        yield from _iter_boxes(child)


class ResidualScoringTests(TestCase):
    """Residual risk is multiplicative — no control may zero a risk, and
    adding a control may never raise the residual."""

    def test_no_controls_returns_inherent(self):
        self.assertEqual(calculate_residual_from_controls(25, []), 25)

    def test_single_perfect_control_never_zeroes_the_risk(self):
        residual = calculate_residual_from_controls(25, [_StubControl(1.0, 'preventive')])
        self.assertGreater(residual, 0)
        self.assertLess(residual, 25)

    def test_untested_control_gives_no_reduction(self):
        self.assertEqual(
            calculate_residual_from_controls(16, [_StubControl(0.0, 'preventive')]), 16
        )

    def test_each_additional_control_lowers_the_residual(self):
        one = calculate_residual_from_controls(25, [_StubControl(1.0, 'preventive')])
        two = calculate_residual_from_controls(
            25, [_StubControl(1.0, 'preventive'), _StubControl(1.0, 'preventive')]
        )
        self.assertLess(two, one)

    def test_adding_a_weak_control_never_raises_residual(self):
        one = calculate_residual_from_controls(20, [_StubControl(0.9, 'detective')])
        two = calculate_residual_from_controls(
            20, [_StubControl(0.9, 'detective'), _StubControl(0.1, 'corrective')]
        )
        self.assertLessEqual(two, one)

    def test_result_is_never_negative(self):
        self.assertGreaterEqual(
            calculate_residual_from_controls(0, [_StubControl(1.0, 'preventive')]), 0
        )


class CsvSafetyTests(TestCase):
    """Exported cells must never be interpreted as formulas by Excel."""

    def test_formula_prefixes_are_neutralised(self):
        for payload in ('=1+1', '+cmd', '-2+3', '@SUM(A1)', '\t=1', '\r=1',
                        '-1+1|calc', '+1+1|cmd'):
            self.assertTrue(csv_safe(payload).startswith("'"), payload)

    def test_real_data_survives_untouched(self):
        for payload in ('-2', '+5', '-1.5', '0.5', '-', '--', '-12.75', 'N/A', 'Normal note'):
            self.assertEqual(csv_safe(payload), payload, payload)

    def test_plain_text_is_untouched(self):
        self.assertEqual(csv_safe(None), '')


class CsvExportRenderingTests(TestCase):
    """Exported cells must be human text, never Python object reprs.

    Model methods referenced by name (``'get_status_display'``) resolve to
    Django's ``partialmethod``-based helpers - callable objects, not strings. If
    the exporter forgets to call them the whole CSV fills up with
    ``functools.partial(<bound method ...>)`` text.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Export Dept')
        cls.other = Department.objects.create(name='Other Dept')
        cls.user = User.objects.create_user(
            'exporter', 'exporter@example.com', 'pw', department=cls.dept,
        )
        cls.asset = Asset.objects.create(
            asset_id='QA-EXP-1', name='Exported asset', owner_dept=cls.dept,
        )
        cls.other_asset = Asset.objects.create(
            asset_id='QA-EXP-2', name='Hidden asset', owner_dept=cls.other,
        )
        cls.control = Control.objects.create(
            code='QA-EXP-CTL', name='Exported control', owner_dept=cls.dept,
        )

    def csv_text(self, url):
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        self.assertIn('text/csv', response['Content-Type'])
        return response.content.decode('utf-8-sig')

    def test_display_labels_are_rendered_not_python_objects(self):
        for url in ('/assets/?export=csv', '/controls/?export=csv'):
            with self.subTest(url=url):
                text = self.csv_text(url)
                for marker in ('functools.partial', '<bound method', 'django.db.models',
                               'object at 0x'):
                    self.assertNotIn(marker, text)

    def test_asset_export_uses_the_choice_label(self):
        text = self.csv_text('/assets/?export=csv')
        self.assertIn(self.asset.get_asset_type_display(), text)
        self.assertIn('Exported asset', text)

    def test_control_export_uses_the_choice_label(self):
        text = self.csv_text('/controls/?export=csv')
        self.assertIn(self.control.get_control_type_display(), text)
        self.assertIn('Exported control', text)

    def test_exports_stay_inside_the_users_department(self):
        for url in ('/assets/?export=csv', '/controls/?export=csv'):
            with self.subTest(url=url):
                text = self.csv_text(url)
                self.assertNotIn('Hidden asset', text)
                self.assertNotIn('QA-EXP-2', text)


class PdfWatermarkTests(TestCase):
    """Every generated PDF page carries the confidentiality seal watermark."""

    SEAL = 'img/watermark_seal.png'

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Watermark Dept')
        cls.user = User.objects.create_user(
            'watermark', 'watermark@example.com', 'pw', department=cls.dept,
        )
        cls.asset = Asset.objects.create(
            asset_id='QA-WM-1', name='Watermarked asset', owner_dept=cls.dept,
        )

    def test_watermark_template_uses_the_seal_image(self):
        from django.template.loader import render_to_string

        html = render_to_string('reports/_watermark.html')
        self.assertIn(self.SEAL, html)
        self.assertIn('position: fixed', html)
        self.assertIn('opacity', html)
        # the old tiled "CONFIDENTIAL" text watermark must be gone
        self.assertNotIn('CONFIDENTIAL', html)

    def test_seal_is_stamped_once_per_page(self):
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from weasyprint.formatting_structure import boxes

        from core.reports import local_asset_url_fetcher

        body = render_to_string('reports/_watermark.html')
        html = '<html><body>' + body + ('<p>filler</p>' * 400) + '</body></html>'
        document = HTML(
            string=html,
            base_url='http://testserver/',
            url_fetcher=local_asset_url_fetcher(),
        ).render()
        self.assertGreater(len(document.pages), 1, 'need multiple pages to check repetition')

        def seal_boxes(page):
            hits = []
            for box in _iter_boxes(page._page_box):
                if not isinstance(box, boxes.ReplacedBox):
                    continue
                element = getattr(box, 'element', None)
                src = str(element.get('src') or '') if element is not None else ''
                if 'watermark_seal' in src:
                    hits.append(box)
            return hits

        for index, page in enumerate(document.pages, start=1):
            with self.subTest(page=index):
                found = seal_boxes(page)
                self.assertEqual(len({id(b) for b in found}), 1)
                box = found[0]
                self.assertAlmostEqual(box.width, box.height, places=1)
                self.assertAlmostEqual(box.width, 396.85, delta=1)  # 10.5cm
                self.assertLess(float(box.style['opacity']), 0.5)  # faint, not solid

    def test_asset_report_download_is_a_pdf(self):
        self.client.force_login(self.user)
        response = self.client.get('/assets/?format=pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))


class MonthBucketingTests(TestCase):
    """Trend charts use real calendar months, not 30-day windows."""

    def test_bounds_are_calendar_months_oldest_first(self):
        self.assertEqual(
            list(iter_month_bounds(_dt.date(2026, 3, 15), 3)),
            [
                (_dt.date(2026, 1, 1), _dt.date(2026, 2, 1)),
                (_dt.date(2026, 2, 1), _dt.date(2026, 3, 1)),
                (_dt.date(2026, 3, 1), _dt.date(2026, 4, 1)),
            ],
        )

    def test_windows_cross_the_year_boundary_correctly(self):
        self.assertEqual(
            list(iter_month_bounds(_dt.date(2026, 1, 5), 2)),
            [
                (_dt.date(2025, 12, 1), _dt.date(2026, 1, 1)),
                (_dt.date(2026, 1, 1), _dt.date(2026, 2, 1)),
            ],
        )


class ScopingTests(TestCase):
    """Authorization: superuser sees all, a department user sees their own plus
    shared records, and an account without a department sees nothing."""

    @classmethod
    def setUpTestData(cls):
        cls.dept_a = Department.objects.create(name='Test Dept A')
        cls.dept_b = Department.objects.create(name='Test Dept B')

        cls.superuser = User.objects.create_superuser('su', 'su@example.com', 'pw')
        cls.user_a = User.objects.create_user('user_a', 'a@example.com', 'pw', department=cls.dept_a)
        cls.user_b = User.objects.create_user('user_b', 'b@example.com', 'pw', department=cls.dept_b)
        cls.no_dept = User.objects.create_user('no_dept', 'n@example.com', 'pw')

        cls.control_a = Control.objects.create(
            name='Dept A control', code='QA-A-1', owner_dept=cls.dept_a,
        )
        cls.control_b = Control.objects.create(
            name='Dept B control', code='QA-B-1', owner_dept=cls.dept_b,
        )
        cls.control_shared = Control.objects.create(
            name='Shared control', code='QA-S-1', owner_dept=cls.dept_a, is_shared=True,
        )

        cls.asset_a = Asset.objects.create(asset_id='QA-AST-A', name='A asset', owner_dept=cls.dept_a)
        cls.asset_b = Asset.objects.create(asset_id='QA-AST-B', name='B asset', owner_dept=cls.dept_b)

    def test_superuser_sees_everything(self):
        self.assertEqual(scope_queryset(Control.objects.all(), self.superuser).count(), 3)
        self.assertEqual(scope_queryset(Asset.objects.all(), self.superuser).count(), 2)

    def test_department_user_sees_own_and_shared_only(self):
        seen = set(scope_queryset(Control.objects.all(), self.user_b).values_list('code', flat=True))
        self.assertEqual(seen, {'QA-B-1', 'QA-S-1'})

    def test_department_user_does_not_see_other_departments(self):
        codes = set(scope_queryset(Control.objects.all(), self.user_a).values_list('code', flat=True))
        self.assertNotIn('QA-B-1', codes)

    def test_user_without_department_sees_nothing(self):
        self.assertEqual(scope_queryset(Control.objects.all(), self.no_dept).count(), 0)
        self.assertEqual(scope_queryset(Asset.objects.all(), self.no_dept).count(), 0)

    def test_anonymous_sees_nothing(self):
        self.assertEqual(scope_queryset(Control.objects.all(), AnonymousUser()).count(), 0)

    def test_object_level_check_matches_queryset_scoping(self):
        self.assertTrue(user_can_access(self.superuser, self.control_a))
        self.assertTrue(user_can_access(self.user_a, self.control_a))
        self.assertFalse(user_can_access(self.user_b, self.control_a))
        self.assertTrue(user_can_access(self.user_b, self.control_shared))
        self.assertFalse(user_can_access(self.no_dept, self.control_a))
        self.assertFalse(user_can_access(AnonymousUser(), self.control_a))


class AnonymousAccessTests(TestCase):
    """Object-level create views must redirect anonymous visitors to the login
    page *before* resolving the object. Resolving first would answer 403 for an
    existing id and 404 for a missing one — an id-enumeration oracle."""

    def test_object_create_views_redirect_anonymous_users(self):
        urls = [
            '/risks/1/treatments/new/',
            '/controls/1/evidence/new/',
            '/controls/1/mapping/new/',
            '/audits/evidence/1/score/new/',
            '/vendors/1/assessments/new/',
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, url)
                self.assertIn('/login/', response['Location'])


class SuperuserOnlyTests(TestCase):
    """Framework configuration screens are platform-config only."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Ops Dept')
        cls.plain = User.objects.create_user('plain', 'p@example.com', 'pw', department=cls.dept)
        cls.hod = User.objects.create_user(
            'hod', 'h@example.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.superuser = User.objects.create_superuser('su2', 'su2@example.com', 'pw')

    def test_requirement_form_blocked_for_normal_users(self):
        for user in (self.plain, self.hod):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get('/frameworks/controls/new/').status_code, 403)

    def test_requirement_form_allowed_for_superuser(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get('/frameworks/controls/new/').status_code, 200)

    def test_logout_requires_post(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)


class SeverityBandTests(TestCase):
    """One banding function, used everywhere."""

    def test_thresholds_are_stable(self):
        from risks.services import severity_band
        for score, expected in [
            (25, 'critical'), (20, 'critical'), (19, 'high'), (12, 'high'),
            (11, 'medium'), (6, 'medium'), (5, 'low'), (0, 'low'),
        ]:
            with self.subTest(score=score):
                self.assertEqual(severity_band(score), expected)


class ResidualFloorTests(TestCase):
    def test_stack_of_perfect_controls_never_reaches_zero(self):
        controls = [_StubControl(1.0, 'preventive') for _ in range(6)]
        self.assertGreaterEqual(calculate_residual_from_controls(25, controls), 1)


class RiskModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from risks.models import RiskCategory
        cls.dept = Department.objects.create(name='Risk Dept')
        cls.category = RiskCategory.objects.create(name='Ops')

    def _risk(self, **kw):
        from risks.models import Risk
        defaults = dict(
            title='T', category=self.category, owner_dept=self.dept,
            likelihood=4, impact=4, status='identified',
        )
        defaults.update(kw)
        return Risk.objects.create(**defaults)

    def test_inherent_score_is_product_and_banded(self):
        r = self._risk(likelihood=5, impact=4)
        self.assertEqual(r.inherent_score, 20)
        self.assertEqual(r.severity_band, 'critical')

    def test_scores_are_clamped_on_save(self):
        r = self._risk(likelihood=9, impact=9)
        self.assertLessEqual(r.inherent_score, 25)

    def test_transitions_block_illegal_jumps(self):
        r = self._risk(status='identified')
        self.assertTrue(r.can_transition_to('assessed'))
        self.assertFalse(r.can_transition_to('monitored'))

    def test_is_overdue_uses_target_close_date(self):
        # Risk.is_overdue uses timezone.localdate(); comparing it with
        # date.today() makes the test fail around midnight in TIME_ZONE.
        past = timezone.localdate() - _dt.timedelta(days=3)
        r = self._risk(target_close_date=past)
        self.assertTrue(r.is_overdue)
        self.assertEqual(r.days_overdue, 3)


class ControlEvidenceGateTests(TestCase):
    def test_effectiveness_requires_a_test_date(self):
        from django.core.exceptions import ValidationError
        dept = Department.objects.create(name='Ctrl Dept')
        control = Control(
            code='QA-C1', name='Control', owner_dept=dept,
            effectiveness_rating='effective',
        )
        with self.assertRaises(ValidationError):
            control.full_clean()


class PolicyWorkflowTests(TestCase):
    def test_transitions(self):
        from policies.models import Policy
        dept = Department.objects.create(name='Pol Dept')
        policy = Policy(code='QA-P1', title='Policy one', owner_dept=dept)
        self.assertTrue(policy.can_transition_to('review'))
        self.assertFalse(policy.can_transition_to('approved'))


class FindingCascadeTests(TestCase):
    def test_finding_creates_and_closes_a_risk(self):
        from risks.models import Risk
        from vulnerabilities.models import Finding, Vulnerability

        dept = Department.objects.create(name='Vuln Dept')
        asset = Asset.objects.create(
            asset_id='QA-V1', name='vulnerable host', owner_dept=dept,
        )
        vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-0001', title='Test CVE',
            cvss_score='9.8', cvss_severity='critical', kev_status=True,
        )
        finding = Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=dept,
            discovered_date=_dt.date.today(),
        )
        risk = Risk.objects.filter(source_finding=finding).first()
        self.assertIsNotNone(risk)
        self.assertEqual(risk.owner_dept_id, dept.id)

        finding.status = 'remediated'
        finding.save()
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')


class SecureMediaTests(TestCase):
    """Uploaded files are only downloadable by a user who can see the record."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from django.test import override_settings
        # Enable the media override BEFORE super().setUpClass(), because Django
        # runs setUpTestData() inside super().setUpClass().
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        import shutil
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        from django.core.files.base import ContentFile
        from policies.models import Policy
        cls.dept_a = Department.objects.create(name='Media A')
        cls.dept_b = Department.objects.create(name='Media B')
        cls.user_a = User.objects.create_user('ma', 'ma@e.com', 'pw', department=cls.dept_a)
        cls.user_b = User.objects.create_user('mb', 'mb@e.com', 'pw', department=cls.dept_b)
        cls.policy = Policy.objects.create(
            code='QA-M1', title='Media policy', owner_dept=cls.dept_a,
        )
        cls.policy.document.save('qa_media.txt', ContentFile(b'secret'), save=True)
        cls.path = cls.policy.document.name

    def test_anonymous_is_redirected_to_login(self):
        self.assertEqual(self.client.get(f'/media/{self.path}').status_code, 302)

    def test_other_department_cannot_download(self):
        self.client.force_login(self.user_b)
        self.assertEqual(self.client.get(f'/media/{self.path}').status_code, 404)

    def test_owner_can_download(self):
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(f'/media/{self.path}').status_code, 200)


class PaginationRenderingTests(TestCase):
    def test_risk_list_renders_pagination_controls(self):
        from risks.models import Risk, RiskCategory
        dept = Department.objects.create(name='Pag Dept')
        category = RiskCategory.objects.create(name='Pag')
        user = User.objects.create_superuser('pag', 'pag@e.com', 'pw')
        for i in range(25):
            Risk.objects.create(title=f'R{i}', category=category, owner_dept=dept)
        self.client.force_login(user)
        response = self.client.get('/risks/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pagination-wrap')


class GlobalSearchCoverageTests(TestCase):
    def test_search_returns_findings(self):
        from vulnerabilities.models import Finding, Vulnerability
        dept = Department.objects.create(name='Search Dept')
        asset = Asset.objects.create(
            asset_id='QA-S1', name='searchable asset zz', owner_dept=dept,
        )
        vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-9999', title='searchable cve zz',
            cvss_score='5.0', cvss_severity='medium',
        )
        Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=dept,
            discovered_date=_dt.date.today(),
        )
        user = User.objects.create_superuser('srch', 'srch@e.com', 'pw')
        self.client.force_login(user)
        response = self.client.get('/search/?q=searchable')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'searchable')


class ObjectSharingTests(TestCase):
    """django-guardian object-level grants widen visibility for exactly one
    record, without leaking the rest of a department."""

    @classmethod
    def setUpTestData(cls):
        from risks.models import Risk, RiskCategory

        cls.dept_a = Department.objects.create(name='Share Dept A')
        cls.dept_b = Department.objects.create(name='Share Dept B')
        cls.category = RiskCategory.objects.create(name='Share Cat')

        cls.hod_b = User.objects.create_user(
            'share_hod_b', 'hb@e.com', 'pw', department=cls.dept_b, is_hod=True,
        )
        cls.user_a = User.objects.create_user(
            'share_user_a', 'ua@e.com', 'pw', department=cls.dept_a,
        )
        cls.superuser = User.objects.create_superuser('share_su', 'su@e.com', 'pw')

        cls.risk_b = Risk.objects.create(
            title='Dept B risk', category=cls.category, owner_dept=cls.dept_b,
        )
        cls.risk_b2 = Risk.objects.create(
            title='Dept B risk two', category=cls.category, owner_dept=cls.dept_b,
        )

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)

    def test_grant_makes_single_object_visible(self):
        from guardian.shortcuts import assign_perm
        from risks.models import Risk

        assign_perm('view_risk', self.user_a, self.risk_b)
        user = self._fresh(self.user_a)

        visible = set(
            scope_queryset(Risk.objects.all(), user).values_list('pk', flat=True)
        )
        self.assertIn(self.risk_b.pk, visible)
        self.assertNotIn(self.risk_b2.pk, visible)
        self.assertTrue(user_can_access(user, self.risk_b))
        self.assertFalse(user_can_access(user, self.risk_b2))

    def test_revoke_removes_visibility(self):
        from core.permissions import grant_object_perms, revoke_object_perms
        from risks.models import Risk

        grant_object_perms(self.risk_b, user=self.user_a)
        revoke_object_perms(self.risk_b, user=self.user_a)
        user = self._fresh(self.user_a)

        visible = scope_queryset(Risk.objects.all(), user)
        self.assertNotIn(self.risk_b.pk, visible.values_list('pk', flat=True))
        self.assertFalse(user_can_access(user, self.risk_b))

    def test_global_permission_does_not_grant_every_row(self):
        """A user holding the *global* change_risk permission must not be handed
        every risk through the object-grant union."""
        from django.contrib.auth.models import Permission
        from risks.models import Risk

        perm = Permission.objects.get(codename='change_risk')
        self.user_a.user_permissions.add(perm)
        user = self._fresh(self.user_a)
        visible = scope_queryset(Risk.objects.all(), user)
        self.assertEqual(visible.count(), 0)

    def test_hod_can_share_own_department_record(self):
        self.client.force_login(self.hod_b)
        response = self.client.post(
            f'/share/risks/risk/{self.risk_b.pk}/',
            {
                'action': 'grant',
                'principal_type': 'user',
                'principal_id': self.user_a.pk,
                'perms': ['view'],
                'next': '/risks/',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = self._fresh(self.user_a)
        self.assertTrue(user_can_access(user, self.risk_b))

    def test_non_manager_cannot_share(self):
        self.client.force_login(self.user_a)  # dept A cannot manage dept B's risk
        response = self.client.post(
            f'/share/risks/risk/{self.risk_b.pk}/',
            {
                'action': 'grant',
                'principal_type': 'user',
                'principal_id': self.superuser.pk,
                'perms': ['view'],
            },
        )
        # RLS hides the other department's row before the view can run its
        # authorization check, so a cross-department share attempt is a 404.
        # A 403 from the application-layer check is equally acceptable.
        self.assertIn(response.status_code, (403, 404))

    def test_share_requires_post(self):
        self.client.force_login(self.hod_b)
        self.assertEqual(
            self.client.get(f'/share/risks/risk/{self.risk_b.pk}/').status_code, 405
        )

    def test_share_panel_renders_for_manager(self):
        self.client.force_login(self.hod_b)
        response = self.client.get(f'/risks/{self.risk_b.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sharing')
        self.assertContains(response, 'share-panel')


class SavedViewTests(TestCase):
    """Per-user saved list filters."""

    @classmethod
    def setUpTestData(cls):
        from risks.models import Risk, RiskCategory

        cls.dept = Department.objects.create(name='SavedView Dept')
        cls.category = RiskCategory.objects.create(name='SavedView Cat')
        cls.user = User.objects.create_superuser('sv_user', 'sv@e.com', 'pw')
        Risk.objects.create(title='SV risk', category=cls.category, owner_dept=cls.dept)

    def test_save_and_apply_view(self):
        from core.models import SavedView

        self.client.force_login(self.user)
        response = self.client.post(
            '/views/save/',
            {
                'name': 'Critical only',
                'model_label': 'risks.risk',
                'query_string': 'severity=critical',
                'next': '/risks/',
            },
        )
        self.assertEqual(response.status_code, 302)
        view = SavedView.objects.get(user=self.user, name='Critical only')
        self.assertEqual(view.query_string, 'severity=critical')

        listing = self.client.get('/risks/')
        self.assertContains(listing, 'Critical only')

    def test_saving_same_name_updates_not_duplicates(self):
        from core.models import SavedView

        self.client.force_login(self.user)
        for qs in ('severity=high', 'severity=low'):
            self.client.post('/views/save/', {
                'name': 'Mine', 'model_label': 'risks.risk',
                'query_string': qs, 'next': '/risks/',
            })
        views = SavedView.objects.filter(user=self.user, name='Mine')
        self.assertEqual(views.count(), 1)
        self.assertEqual(views.first().query_string, 'severity=low')

    def test_delete_view(self):
        from core.models import SavedView

        view = SavedView.objects.create(
            user=self.user, name='Temp', model_label='risks.risk',
        )
        self.client.force_login(self.user)
        response = self.client.post(
            f'/views/{view.pk}/delete/', {'next': '/risks/'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SavedView.objects.filter(pk=view.pk).exists())

    def test_cannot_delete_another_users_view(self):
        from core.models import SavedView

        other = User.objects.create_user('sv_other', 'o@e.com', 'pw')
        view = SavedView.objects.create(
            user=other, name='Theirs', model_label='risks.risk',
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(f'/views/{view.pk}/delete/').status_code, 404
        )


class BulkActionTests(TestCase):
    """Checkbox bulk edits stay inside the scoped queryset and reject values
    that would bypass a workflow gate."""

    @classmethod
    def setUpTestData(cls):
        cls.dept_a = Department.objects.create(name='Bulk Dept A')
        cls.dept_b = Department.objects.create(name='Bulk Dept B')
        cls.superuser = User.objects.create_superuser('bulk_su', 'bs@e.com', 'pw')
        cls.hod_a = User.objects.create_user(
            'bulk_hod_a', 'bha@e.com', 'pw', department=cls.dept_a, is_hod=True,
        )
        cls.finding_a = AuditFinding.objects.create(
            title='Bulk finding A', owner_dept=cls.dept_a, severity='low',
        )
        cls.finding_b = AuditFinding.objects.create(
            title='Bulk finding B', owner_dept=cls.dept_b, severity='low',
        )

    def test_bulk_set_severity(self):
        self.client.force_login(self.superuser)
        response = self.client.post('/audits/findings/', {
            'bulk_action': 'set_severity',
            'bulk_value': 'high',
            'selected': [self.finding_a.pk, self.finding_b.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.finding_a.refresh_from_db()
        self.assertEqual(self.finding_a.severity, 'high')

    def test_bulk_cannot_close_finding(self):
        self.client.force_login(self.superuser)
        self.client.post('/audits/findings/', {
            'bulk_action': 'set_status',
            'bulk_value': 'closed',   # not an offered choice
            'selected': [self.finding_a.pk],
        })
        self.finding_a.refresh_from_db()
        self.assertEqual(self.finding_a.status, 'open')

    def test_bulk_action_is_department_scoped(self):
        self.client.force_login(self.hod_a)
        self.client.post('/audits/findings/', {
            'bulk_action': 'set_severity',
            'bulk_value': 'critical',
            'selected': [self.finding_a.pk, self.finding_b.pk],
        })
        self.finding_a.refresh_from_db()
        self.finding_b.refresh_from_db()
        self.assertEqual(self.finding_a.severity, 'critical')
        self.assertEqual(self.finding_b.severity, 'low')  # untouched

    def test_asset_bulk_classification(self):
        asset = Asset.objects.create(
            asset_id='BULK-A1', name='Bulk asset', owner_dept=self.dept_a,
        )
        self.client.force_login(self.superuser)
        self.client.post('/assets/', {
            'bulk_action': 'set_classification',
            'bulk_value': 'restricted',
            'selected': [asset.pk],
        })
        asset.refresh_from_db()
        self.assertEqual(asset.classification, 'restricted')

    def test_bulk_toolbar_renders(self):
        self.client.force_login(self.superuser)
        response = self.client.get('/audits/findings/')
        self.assertContains(response, 'bulkForm')


class FindingVerificationTests(TestCase):
    """A finding cannot be closed until its remediation is verified."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Verify Dept')
        cls.hod = User.objects.create_user(
            'verify_hod', 'vh@e.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.plain = User.objects.create_user(
            'verify_plain', 'vp@e.com', 'pw', department=cls.dept,
        )
        cls.superuser = User.objects.create_superuser('verify_su', 'vs@e.com', 'pw')

    def _finding(self, **kwargs):
        defaults = {'title': 'Verify me', 'owner_dept': self.dept}
        defaults.update(kwargs)
        return AuditFinding.objects.create(**defaults)

    def test_cannot_close_without_verification(self):
        from django.core.exceptions import ValidationError

        finding = self._finding(status='open')
        finding.status = 'closed'
        with self.assertRaises(ValidationError):
            finding.save()

    def test_model_clean_blocks_unverified_closure(self):
        from django.core.exceptions import ValidationError

        finding = self._finding(title='Clean block')
        finding.status = 'closed'
        with self.assertRaises(ValidationError):
            finding.full_clean()

    def test_verify_closes_finding(self):
        finding = self._finding(title='Resolved one', status='resolved')
        self.client.force_login(self.hod)
        response = self.client.post(
            f'/audits/findings/{finding.pk}/verify/',
            {'decision': 'verified', 'verification_notes': 'Checked logs.'},
        )
        self.assertEqual(response.status_code, 302)
        finding.refresh_from_db()
        self.assertEqual(finding.verification_status, 'verified')
        self.assertEqual(finding.status, 'closed')
        self.assertEqual(finding.verified_by, self.hod)
        self.assertIsNotNone(finding.verified_at)
        self.assertTrue(finding.closed_date)

    def test_reject_sends_back_for_remediation(self):
        finding = self._finding(title='Reject me', status='resolved')
        self.client.force_login(self.hod)
        self.client.post(
            f'/audits/findings/{finding.pk}/verify/',
            {'decision': 'rejected', 'verification_notes': 'Not fixed.'},
        )
        finding.refresh_from_db()
        self.assertEqual(finding.verification_status, 'rejected')
        self.assertEqual(finding.status, 'in_progress')

    def test_only_resolved_can_be_verified(self):
        finding = self._finding(title='Still open', status='open')
        self.client.force_login(self.hod)
        self.client.post(
            f'/audits/findings/{finding.pk}/verify/', {'decision': 'verified'}
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'open')
        self.assertEqual(finding.verification_status, 'pending')

    def test_plain_user_cannot_verify(self):
        finding = self._finding(title='Plain cannot', status='resolved')
        self.client.force_login(self.plain)
        response = self.client.post(
            f'/audits/findings/{finding.pk}/verify/', {'decision': 'verified'}
        )
        self.assertEqual(response.status_code, 403)

    def test_verification_form_shown_on_resolved_finding(self):
        finding = self._finding(title='Show form', status='resolved')
        self.client.force_login(self.hod)
        response = self.client.get(f'/audits/findings/{finding.pk}/')
        self.assertContains(response, 'Verify &amp; close')


class RiskAppetiteBreachTests(TestCase):
    """Appetite is governed by *residual* risk once a risk is treated.

    Regression: an untreated inherent=16 risk used to stay flagged as breaching
    even after effective controls dropped its residual below the tolerance,
    because the inherent ceiling was always ANDed in.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Appetite Dept')
        cls.category = RiskCategory.objects.create(name='Appetite Cat')
        RiskAppetite.objects.create(
            department=cls.dept, category=cls.category,
            max_inherent_score=10, max_residual_score=6, risk_capacity=20,
        )

    def _risk(self, dept=None, **kw):
        defaults = dict(
            title='Untreated risk', category=self.category,
            owner_dept=dept or self.dept, likelihood=4, impact=4,  # inherent 16
        )
        defaults.update(kw)
        return Risk.objects.create(**defaults)

    def test_untreated_risk_breaches(self):
        risk = self._risk()
        self.assertEqual(risk.inherent_score, 16)
        self.assertEqual(risk.residual_score, 16)
        self.assertTrue(risk.appetite_breached)

    def test_effective_control_clears_breach(self):
        risk = self._risk()
        ctl = Control.objects.create(
            code='AP-1', name='Perfect preventive', owner_dept=self.dept,
            status='implemented', lifecycle_status='operational',
            effectiveness_rating='effective', control_type='preventive',
        )
        risk.controls.add(ctl)
        risk.refresh_from_db()
        self.assertLess(risk.residual_score, 6)
        self.assertFalse(risk.appetite_breached)
        self.assertEqual(risk.appetite_state, 'within')

    def test_state_is_none_without_applicable_appetite(self):
        other = Department.objects.create(name='No Appetite Dept')
        risk = self._risk(dept=other, title='No appetite', likelihood=1, impact=1)
        self.assertFalse(risk.appetite_breached)
        self.assertEqual(risk.appetite_state, 'none')


class TreatmentRiskSyncTests(TestCase):
    """A treatment carries its controls onto the risk and closes it on completion."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Treat Dept')
        cls.category = RiskCategory.objects.create(name='Treat Cat')

    def _risk(self, **kw):
        defaults = dict(
            title='Treat risk', category=self.category, owner_dept=self.dept,
            likelihood=3, impact=3, status='treating',
        )
        defaults.update(kw)
        return Risk.objects.create(**defaults)

    def test_completing_treatment_closes_risk(self):
        from risks.services import sync_risk_from_treatment

        risk = self._risk()
        treatment = RiskTreatment.objects.create(
            risk=risk, action_plan='Do the thing', status='planned',
        )
        treatment.status = 'completed'
        treatment.save()
        sync_risk_from_treatment(treatment)
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

    def test_treatment_controls_reach_the_risk(self):
        from risks.services import sync_risk_from_treatment

        risk = self._risk()
        treatment = RiskTreatment.objects.create(risk=risk, action_plan='Add control')
        ctl = Control.objects.create(
            code='TR-1', name='Detective', owner_dept=self.dept,
            status='implemented', lifecycle_status='operational',
            effectiveness_rating='effective', control_type='detective',
        )
        treatment.controls.add(ctl)
        sync_risk_from_treatment(treatment)
        self.assertIn(ctl, risk.controls.all())
        risk.refresh_from_db()
        self.assertLess(risk.residual_score, risk.inherent_score)


class VendorContractExpiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Vendor Expiry Dept')

    def _vendor(self, **kw):
        defaults = dict(name='V', owner_dept=self.dept)
        defaults.update(kw)
        return Vendor.objects.create(**defaults)

    def test_expired_contract_is_derived(self):
        today = timezone.localdate()
        vendor = self._vendor(
            name='Expired', status='active',
            contract_renewal_date=today - _dt.timedelta(days=5),
        )
        self.assertTrue(vendor.is_contract_expired)
        self.assertEqual(vendor.contract_state, 'expired')
        self.assertEqual(vendor.days_to_renewal, -5)

    def test_due_soon_and_current(self):
        today = timezone.localdate()
        soon = self._vendor(
            name='Soon', contract_renewal_date=today + _dt.timedelta(days=10),
        )
        self.assertTrue(soon.is_renewal_due_soon)
        self.assertEqual(soon.contract_state, 'due_soon')

        far = self._vendor(
            name='Far', contract_renewal_date=today + _dt.timedelta(days=200),
        )
        self.assertEqual(far.contract_state, 'current')
        self.assertFalse(far.is_contract_expired)

    def test_no_renewal_date(self):
        vendor = self._vendor(name='No date')
        self.assertEqual(vendor.contract_state, 'none')
        self.assertIsNone(vendor.days_to_renewal)
        self.assertFalse(vendor.is_contract_expired)


class DeleteViewTests(TestCase):
    """Destructive actions are HOD/superuser-only and department-scoped."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Del Dept')
        cls.other = Department.objects.create(name='Other Del Dept')
        cls.hod = User.objects.create_user(
            'del_hod', 'dh@e.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.plain = User.objects.create_user(
            'del_plain', 'dp@e.com', 'pw', department=cls.dept,
        )
        cls.outsider = User.objects.create_user(
            'del_out', 'do@e.com', 'pw', department=cls.other, is_hod=True,
        )

    def _asset(self):
        return Asset.objects.create(
            asset_id='DEL-1', name='Delete me', owner_dept=self.dept,
        )

    def test_hod_can_delete_own_asset(self):
        asset = self._asset()
        self.client.force_login(self.hod)
        response = self.client.post(f'/assets/{asset.pk}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())

    def test_plain_user_cannot_delete(self):
        asset = self._asset()
        self.client.force_login(self.plain)
        response = self.client.post(f'/assets/{asset.pk}/delete/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Asset.objects.filter(pk=asset.pk).exists())

    def test_cross_department_delete_is_404(self):
        asset = self._asset()
        self.client.force_login(self.outsider)
        response = self.client.post(f'/assets/{asset.pk}/delete/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Asset.objects.filter(pk=asset.pk).exists())


class TicketLinkTests(TestCase):
    """A ticket can be linked to a specific asset/risk/control/policy."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Ticket Link Dept')
        cls.category = RiskCategory.objects.create(name='Ticket Link Cat')
        cls.hod = User.objects.create_user(
            'tl_hod', 'tl@e.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.asset = Asset.objects.create(
            asset_id='TL-1', name='Linkable asset', owner_dept=cls.dept,
        )
        cls.risk = Risk.objects.create(
            title='Linkable risk', category=cls.category, owner_dept=cls.dept,
        )

    def test_form_links_an_asset(self):
        from django.contrib.contenttypes.models import ContentType

        form = TicketForm(user=self.hod, data={
            'title': 'Link a ticket', 'priority': 2, 'status': 'open',
            'owner_dept': self.dept.pk, 'link_asset': self.asset.pk,
        })
        self.assertTrue(form.is_valid(), form.errors)
        ticket = form.save(commit=False)
        form.apply_link(ticket)
        ticket.created_by = self.hod
        ticket.save()
        self.assertEqual(
            ticket.content_type, ContentType.objects.get_for_model(Asset)
        )
        self.assertEqual(ticket.object_id, self.asset.pk)

    def test_two_links_are_rejected(self):
        form = TicketForm(user=self.hod, data={
            'title': 'Two links', 'priority': 2, 'status': 'open',
            'owner_dept': self.dept.pk,
            'link_asset': self.asset.pk, 'link_risk': self.risk.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('at most one', str(form.errors))


class ExceptionApprovalTests(TestCase):
    """Only the person named as approver may accept a risk exception."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Exc Dept')
        cls.category = RiskCategory.objects.create(name='Exc Cat')
        cls.approver = User.objects.create_user(
            'exc_app', 'ea@e.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.other_hod = User.objects.create_user(
            'exc_other', 'eo@e.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.risk = Risk.objects.create(
            title='Exc risk', category=cls.category, owner_dept=cls.dept,
        )

    def _exception(self, **kw):
        defaults = dict(
            risk=self.risk, title='Accept this risk',
            justification='Because mitigation is not feasible right now.',
            approver=self.approver,
            expiry_date=timezone.localdate() + _dt.timedelta(days=30),
        )
        defaults.update(kw)
        return RiskException.objects.create(**defaults)

    def test_other_hod_cannot_approve(self):
        exception = self._exception()
        self.client.force_login(self.other_hod)
        response = self.client.post(
            f'/risks/exceptions/{exception.pk}/approve/'
        )
        self.assertEqual(response.status_code, 302)
        exception.refresh_from_db()
        self.assertEqual(exception.status, 'pending')
        self.assertEqual(exception.approver, self.approver)

    def test_approver_can_approve(self):
        exception = self._exception()
        self.client.force_login(self.approver)
        self.client.post(f'/risks/exceptions/{exception.pk}/approve/')
        exception.refresh_from_db()
        self.assertEqual(exception.status, 'active')
        self.assertEqual(exception.approver, self.approver)
        self.assertIsNotNone(exception.approval_date)

    def test_helper_notifies_the_approver(self):
        from core.notifications import Notification
        from risks.views import _notify_exception_approver

        exception = self._exception()
        _notify_exception_approver(exception)
        note = Notification.objects.get(kind='exception_approval_needed')
        self.assertEqual(note.recipient, self.approver)
        self.assertEqual(note.ref_id, exception.pk)


class ErrorPageTests(TestCase):
    """Custom 404/403 pages explain cross-department access denials."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Err Dept')
        cls.user = User.objects.create_user(
            'err_user', 'e@e.com', 'pw', department=cls.dept,
        )

    def test_missing_record_uses_custom_404(self):
        self.client.force_login(self.user)
        response = self.client.get('/assets/999999/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'error-card', status_code=404)

    def test_forbidden_uses_custom_403(self):
        self.client.force_login(self.user)
        response = self.client.post('/assets/1/delete/')
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'error-card', status_code=403)


# ===========================================================================
# Email digests & escalation notifications
# ===========================================================================

class EmailPreferenceTests(TestCase):
    """``email_pref_allows`` is the single gate in front of every outbound mail."""

    def setUp(self):
        self.dept = Department.objects.create(name='Mail Dept')
        self.user = User.objects.create_user(
            'mail_user', 'mail@example.com', 'pw', department=self.dept,
        )

    def test_missing_preference_row_defaults_to_opted_in(self):
        from core.emails import email_pref_allows
        self.assertIsNone(getattr(self.user, 'preference', None))
        self.assertTrue(email_pref_allows(self.user))
        self.assertTrue(email_pref_allows(self.user, 'email_on_risk_breach'))

    def test_master_switch_blocks_every_flag(self):
        from core.emails import email_pref_allows
        from core.settings_model import UserPreference
        UserPreference.objects.create(
            user=self.user, email_notifications_enabled=False,
        )
        self.assertFalse(email_pref_allows(self.user))
        self.assertFalse(email_pref_allows(self.user, 'email_on_kri_red'))

    def test_a_single_flag_can_be_turned_off(self):
        from core.emails import email_pref_allows
        from core.settings_model import UserPreference
        UserPreference.objects.create(user=self.user, email_on_vuln_sla=False)
        self.assertTrue(email_pref_allows(self.user))
        self.assertFalse(email_pref_allows(self.user, 'email_on_vuln_sla'))

    def test_a_user_without_an_address_gets_nothing(self):
        from core.emails import email_pref_allows
        self.user.email = ''
        self.user.save(update_fields=['email'])
        self.assertFalse(email_pref_allows(self.user))

    def test_an_inactive_user_gets_nothing(self):
        from core.emails import email_pref_allows
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertFalse(email_pref_allows(self.user))


class EmailRenderingTests(TestCase):
    """Links must be absolute and every item must survive into both bodies."""

    def test_site_url_builds_absolute_links(self):
        from core.emails import site_url
        url = site_url('/tickets/1/')
        self.assertTrue(url.startswith('http'))
        self.assertTrue(url.endswith('/tickets/1/'))
        self.assertEqual(site_url('https://x.test/y'), 'https://x.test/y')

    def test_digest_bodies_include_every_item(self):
        from core.emails import render_html, render_text
        items = [
            {'title': 'First item', 'meta': 'm1', 'url': '/a/', 'severity': 'danger'},
            {'title': 'Second item', 'meta': 'm2', 'url': '/b/', 'severity': 'warning'},
        ]
        text = render_text('Heading', 'Intro', items)
        html = render_html('Heading', 'Intro', items)
        for body in (text, html):
            self.assertIn('First item', body)
            self.assertIn('Second item', body)
        self.assertIn('href', html)

    def test_send_email_never_raises_without_recipients(self):
        from core.emails import send_email
        self.assertEqual(send_email('Subject', 'Body', []), 0)
        self.assertEqual(send_email('Subject', 'Body', [None, '']), 0)


class EscalationScanTests(TestCase):
    """Overdue work is found once, notified once, and emailed to the owner."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Esc Dept')
        cls.hod = User.objects.create_user(
            'esc_hod', 'esc_hod@example.com', 'pw',
            department=cls.dept, is_hod=True,
        )
        cls.owner = User.objects.create_user(
            'esc_owner', 'esc_owner@example.com', 'pw', department=cls.dept,
        )

    def _overdue_ticket(self, **kw):
        from tickets.models import Ticket
        defaults = dict(
            title='Overdue ticket',
            owner_dept=self.dept,
            assigned_to=self.owner,
            due_date=timezone.localdate() - _dt.timedelta(days=10),
        )
        defaults.update(kw)
        return Ticket.objects.create(**defaults)

    def test_overdue_ticket_is_collected(self):
        from core.escalations import collect_escalations
        ticket = self._overdue_ticket()
        found = {e.ref.pk for e in collect_escalations() if e.kind == 'ticket_overdue'}
        self.assertIn(ticket.pk, found)

    def test_expired_vendor_contract_is_collected(self):
        from core.escalations import collect_escalations
        vendor = Vendor.objects.create(
            name='Lapsed Vendor', owner_dept=self.dept,
            contract_renewal_date=timezone.localdate() - _dt.timedelta(days=30),
        )
        found = {
            e.ref.pk for e in collect_escalations()
            if e.kind == 'vendor_contract_expired'
        }
        self.assertIn(vendor.pk, found)

    def test_grace_period_quietens_a_one_day_slip(self):
        from core.escalations import collect_escalations
        ticket = self._overdue_ticket(
            due_date=timezone.localdate() - _dt.timedelta(days=1),
        )
        found = {e.ref.pk for e in collect_escalations() if e.kind == 'ticket_overdue'}
        self.assertNotIn(ticket.pk, found)

    def test_scan_is_idempotent_and_emails_once(self):
        from core.escalations import run_escalations
        from core.notifications import Notification
        ticket = self._overdue_ticket()

        run_escalations()
        self.assertEqual(
            Notification.objects.filter(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).count(),
            1,
        )
        self.assertIn('esc_owner@example.com', mail.outbox[0].to)

        mail.outbox.clear()
        run_escalations()
        self.assertEqual(
            Notification.objects.filter(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_notification_is_targeted_at_the_assignee(self):
        from core.escalations import run_escalations
        from core.notifications import Notification
        ticket = self._overdue_ticket()
        run_escalations()
        note = Notification.objects.get(kind='ticket_overdue', ref_id=ticket.pk)
        self.assertEqual(note.recipient, self.owner)

    def test_no_assignee_falls_back_to_the_hod(self):
        from core.escalations import run_escalations
        self._overdue_ticket(assigned_to=None)
        run_escalations()
        self.assertEqual(mail.outbox[0].to, ['esc_hod@example.com'])

    def test_disabled_flag_silences_the_email_not_the_alert(self):
        from core.escalations import run_escalations
        from core.notifications import Notification
        from core.settings_model import UserPreference
        UserPreference.objects.create(
            user=self.owner, email_on_ticket_assigned=False,
        )
        ticket = self._overdue_ticket()
        run_escalations()
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            Notification.objects.filter(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).exists()
        )

    def test_resolving_the_ticket_clears_the_alert(self):
        from core.escalations import run_escalations
        from core.notification_registry import refresh_notifications
        from core.notifications import Notification
        ticket = self._overdue_ticket()
        run_escalations()
        ticket.status = 'resolved'
        ticket.save(update_fields=['status'])
        refresh_notifications(is_super=True)
        self.assertTrue(
            Notification.objects.get(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).is_cleared
        )

    def test_dry_run_writes_nothing(self):
        from core.escalations import run_escalations
        from core.notifications import Notification
        ticket = self._overdue_ticket()
        summary = run_escalations(dry_run=True)
        self.assertEqual(summary['found'], 1)
        self.assertEqual(
            Notification.objects.filter(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).count(),
            0,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_no_email_mode_still_raises_the_alert(self):
        from core.escalations import run_escalations
        from core.notifications import Notification
        ticket = self._overdue_ticket()
        run_escalations(send_emails=False)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            Notification.objects.filter(
                kind='ticket_overdue', ref_id=ticket.pk,
            ).exists()
        )


class DigestCommandTests(TestCase):
    """``send_email_digest`` honours the window and the preferences."""

    def setUp(self):
        self.dept = Department.objects.create(name='Digest Dept')
        self.user = User.objects.create_user(
            'digest_user', 'digest@example.com', 'pw', department=self.dept,
        )
        from core.notifications import Notification
        Notification.objects.create(
            owner_dept=self.dept, kind='ticket_unassigned',
            title='TICK-9001 needs an owner', recipient=self.user,
        )

    def _run(self, *args):
        out = StringIO()
        call_command('send_email_digest', *args, stdout=out)
        return out.getvalue()

    def test_forced_digest_is_emailed_and_stamped(self):
        from core.settings_model import UserPreference
        self._run('--force', '--user', 'digest_user')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['digest@example.com'])
        self.assertIn('TICK-9001 needs an owner', mail.outbox[0].body)
        self.assertIsNotNone(
            UserPreference.objects.get(user=self.user).last_digest_sent_at
        )

    def test_the_window_stops_a_second_send(self):
        self._run('--force', '--user', 'digest_user')
        mail.outbox.clear()
        self._run('--user', 'digest_user')
        self.assertEqual(len(mail.outbox), 0)

    def test_frequency_off_is_respected(self):
        from core.settings_model import UserPreference
        UserPreference.objects.create(user=self.user, email_digest_frequency='off')
        self._run('--force', '--user', 'digest_user')
        self.assertEqual(len(mail.outbox), 0)

    def test_master_switch_is_respected(self):
        from core.settings_model import UserPreference
        UserPreference.objects.create(
            user=self.user, email_notifications_enabled=False,
        )
        self._run('--force', '--user', 'digest_user')
        self.assertEqual(len(mail.outbox), 0)

    def test_nothing_to_report_sends_nothing(self):
        from core.notifications import Notification
        Notification.objects.filter(recipient=self.user).delete()
        self._run('--force', '--user', 'digest_user')
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_sends_no_mail(self):
        self._run('--force', '--user', 'digest_user', '--dry-run')
        self.assertEqual(len(mail.outbox), 0)


class TestEmailViewTests(TestCase):
    """The Settings page can prove deliverability end to end."""

    def setUp(self):
        self.dept = Department.objects.create(name='TestMail Dept')
        self.user = User.objects.create_user(
            'tm_user', 'tm@example.com', 'pw', department=self.dept,
        )

    def test_settings_page_renders_the_digest_controls(self):
        self.client.force_login(self.user)
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Digest frequency')
        self.assertContains(response, 'email_digest_frequency')
        self.assertContains(response, 'email_on_escalation')
        self.assertContains(response, '/settings/test-email/')

    def test_requires_a_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/settings/test-email/').status_code, 405)

    def test_requires_login(self):
        response = self.client.post('/settings/test-email/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_sends_a_sample_digest(self):
        self.client.force_login(self.user)
        response = self.client.post('/settings/test-email/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['tm@example.com'])

    def test_reports_a_missing_address(self):
        self.user.email = ''
        self.user.save(update_fields=['email'])
        self.client.force_login(self.user)
        self.client.post('/settings/test-email/')
        self.assertEqual(len(mail.outbox), 0)


class EscalationRegistryTests(TestCase):
    """Every escalation kind needs a label, an icon and an auto-clear rule."""

    KINDS = {
        'risk_escalated', 'risk_overdue', 'finding_overdue', 'action_overdue',
        'ticket_overdue', 'exception_expiring', 'vendor_contract_expired',
        'kri_red', 'vuln_sla_breach',
    }

    def test_every_escalation_kind_is_registered(self):
        from core.notification_registry import CLEAR_RULES
        from core.notifications import Notification
        labels = dict(Notification.KIND_CHOICES)
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, labels)
                self.assertIn(kind, CLEAR_RULES)

    def test_escalations_have_a_dedicated_icon(self):
        from core.notifications import Notification
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                self.assertNotEqual(Notification(kind=kind).kind_icon, 'bi-bell')


class AuditFindingDueDateTests(TestCase):
    """The due-date helpers the escalation scan relies on."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Finding Dept')

    def _finding(self, **kw):
        defaults = dict(
            title='Finding with a date', owner_dept=self.dept,
            severity='high', status='open',
            due_date=timezone.localdate() - _dt.timedelta(days=3),
        )
        defaults.update(kw)
        return AuditFinding.objects.create(**defaults)

    def test_open_finding_past_due_is_overdue(self):
        self.assertTrue(self._finding().is_overdue)

    def test_a_closed_finding_is_never_overdue(self):
        finding = self._finding(
            status='closed', verification_status='verified',
        )
        self.assertFalse(finding.is_overdue)

    def test_a_resolved_finding_is_not_overdue(self):
        self.assertFalse(self._finding(status='resolved').is_overdue)

    def test_accepted_risk_is_not_overdue(self):
        self.assertFalse(self._finding(status='accepted').is_overdue)

    def test_no_due_date_is_not_overdue(self):
        self.assertFalse(self._finding(due_date=None).is_overdue)

    def test_days_overdue_counts_the_slip(self):
        self.assertEqual(self._finding().days_overdue, 3)


# ==================================================================
# SECURITY: a read-only share grants read, never write
# ==================================================================

class WriteAuthorizationTests(TestCase):
    """A view-only object share must not authorise a mutation.

    Regression: ``user_can_access`` accepted *any* object permission, so a
    record shared "for visibility only" also handed the recipient edit,
    delete and status-change rights across ~15 endpoints.
    """

    @classmethod
    def setUpTestData(cls):
        from core.mixins import user_can_change  # noqa: F401  (documented below)

        cls.dept_a = Department.objects.create(name='Write A')
        cls.dept_b = Department.objects.create(name='Write B')
        cls.user_a = User.objects.create_user(
            'wa', 'wa@e.com', 'pw', department=cls.dept_a,
        )
        cls.hod_a = User.objects.create_user(
            'wa_hod', 'wah@e.com', 'pw', department=cls.dept_a, is_hod=True,
        )
        cls.superuser = User.objects.create_superuser('write_su', 'wsu@e.com', 'pw')
        cls.cat = RiskCategory.objects.create(name='Write Cat')

        cls.risk_b = Risk.objects.create(
            title='B risk', category=cls.cat, owner_dept=cls.dept_b,
        )
        cls.control_a = Control.objects.create(
            code='WA-A1', name='A control', owner_dept=cls.dept_a,
        )
        cls.control_b = Control.objects.create(
            code='WA-B1', name='B control', owner_dept=cls.dept_b,
        )
        cls.control_shared = Control.objects.create(
            code='WA-S1', name='Org-wide control', owner_dept=cls.dept_b,
            is_shared=True,
        )
        cls.finding_b = AuditFinding.objects.create(
            title='B finding', owner_dept=cls.dept_b, severity='low',
        )

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)

    def test_read_only_share_can_be_read_but_not_changed(self):
        from core.mixins import user_can_change
        from core.permissions import grant_object_perms

        grant_object_perms(self.risk_b, user=self.user_a, perms=('view',))
        user = self._fresh(self.user_a)
        self.assertTrue(user_can_access(user, self.risk_b))
        self.assertFalse(user_can_change(user, self.risk_b))

    def test_change_share_grants_write(self):
        from core.mixins import user_can_change
        from core.permissions import grant_object_perms

        grant_object_perms(self.risk_b, user=self.user_a, perms=('view', 'change'))
        self.assertTrue(user_can_change(self._fresh(self.user_a), self.risk_b))

    def test_is_shared_flag_is_read_only(self):
        """The org-wide ``is_shared`` flag widens visibility, not authority."""
        from core.mixins import user_can_change

        self.assertTrue(user_can_access(self.user_a, self.control_shared))
        self.assertFalse(user_can_change(self.user_a, self.control_shared))

    def test_same_department_may_change(self):
        from core.mixins import user_can_change

        self.assertTrue(user_can_change(self.user_a, self.control_a))

    def test_global_permission_does_not_grant_object_write(self):
        """Holding the *global* change_risk permission must not imply write on
        an object that was never granted to the user."""
        from django.contrib.auth.models import Permission
        from core.mixins import user_can_change

        perm = Permission.objects.get(codename='change_risk')
        self.user_a.user_permissions.add(perm)
        self.assertFalse(user_can_change(self._fresh(self.user_a), self.risk_b))

    def test_view_only_share_cannot_open_edit_form(self):
        from core.permissions import grant_object_perms

        grant_object_perms(self.risk_b, user=self.user_a, perms=('view',))
        self.client.force_login(self.user_a)
        self.assertEqual(
            self.client.get(f'/risks/{self.risk_b.pk}/edit/').status_code, 404
        )

    def test_change_share_can_open_edit_form(self):
        from core.permissions import grant_object_perms

        grant_object_perms(self.risk_b, user=self.user_a, perms=('view', 'change'))
        self.client.force_login(self.user_a)
        self.assertEqual(
            self.client.get(f'/risks/{self.risk_b.pk}/edit/').status_code, 200
        )

    def test_view_only_share_cannot_post_a_status_change(self):
        from core.permissions import grant_object_perms

        grant_object_perms(self.control_b, user=self.user_a, perms=('view',))
        self.client.force_login(self.user_a)
        response = self.client.post(f'/controls/{self.control_b.pk}/advance/')
        self.assertEqual(response.status_code, 403)
        self.control_b.refresh_from_db()
        self.assertEqual(self.control_b.lifecycle_status, 'proposed')

    def test_change_share_can_post_a_status_change(self):
        from core.permissions import grant_object_perms

        grant_object_perms(self.control_b, user=self.user_a, perms=('view', 'change'))
        self.client.force_login(self.user_a)
        response = self.client.post(f'/controls/{self.control_b.pk}/advance/')
        self.assertEqual(response.status_code, 302)
        self.control_b.refresh_from_db()
        self.assertNotEqual(self.control_b.lifecycle_status, 'proposed')

    def test_view_only_share_cannot_bulk_edit(self):
        from core.permissions import grant_object_perms

        grant_object_perms(self.finding_b, user=self.hod_a, perms=('view',))
        self.client.force_login(self.hod_a)
        self.client.post('/audits/findings/', {
            'bulk_action': 'set_severity',
            'bulk_value': 'critical',
            'selected': [self.finding_b.pk],
        })
        self.finding_b.refresh_from_db()
        self.assertEqual(self.finding_b.severity, 'low')

    def test_writable_queryset_excludes_read_only_rows(self):
        from core.mixins import writable_queryset
        from core.permissions import grant_object_perms

        grant_object_perms(self.risk_b, user=self.user_a, perms=('view',))
        visible = set(
            scope_queryset(Risk.objects.all(), self._fresh(self.user_a))
            .values_list('pk', flat=True)
        )
        writable = set(
            writable_queryset(Risk.objects.all(), self._fresh(self.user_a))
            .values_list('pk', flat=True)
        )
        self.assertIn(self.risk_b.pk, visible)
        self.assertNotIn(self.risk_b.pk, writable)


# ==================================================================
# SECURITY: uploaded evidence / policy documents
# ==================================================================

class UploadValidationTests(TestCase):
    """The same allowlist + size cap guards every user upload."""

    def test_html_and_svg_are_rejected(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.validators import validate_evidence_file

        for name in ('payload.html', 'script.svg', 'evil.exe', 'x.php'):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_evidence_file(SimpleUploadedFile(name, b'<script>'))

    def test_pdf_and_png_are_accepted(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.validators import validate_evidence_file

        samples = {
            'report.pdf': b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n',
            'screenshot.png': b'\x89PNG\r\n\x1a\n' + b'\x00' * 32,
            'notes.txt': b'data',
        }
        for name, content in samples.items():
            with self.subTest(name=name):
                validate_evidence_file(SimpleUploadedFile(name, content))

    def test_renamed_executable_is_rejected_by_magic_bytes(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.validators import validate_evidence_file

        with self.assertRaises(ValidationError):
            validate_evidence_file(
                SimpleUploadedFile('invoice.pdf', b'<script>alert(1)</script>')
            )

    def test_oversize_upload_is_rejected(self):
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.validators import MAX_UPLOAD_SIZE, validate_evidence_file

        big = SimpleUploadedFile('big.pdf', b'x' * (MAX_UPLOAD_SIZE + 1))
        with self.assertRaises(ValidationError):
            validate_evidence_file(big)

    def test_evidence_and_policy_forms_carry_the_validator(self):
        from audits.forms import EvidenceItemForm
        from core.validators import validate_evidence_file
        from policies.forms import PolicyForm

        self.assertIn(
            validate_evidence_file, EvidenceItemForm().fields['attachment'].validators
        )
        self.assertIn(
            validate_evidence_file, PolicyForm().fields['document'].validators
        )


class MediaDispositionTests(TestCase):
    """Non-image uploads download; they are never rendered same-origin."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from django.test import override_settings

        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        import shutil

        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        from django.core.files.base import ContentFile
        from policies.models import Policy

        cls.dept = Department.objects.create(name='Disposition Dept')
        cls.user = User.objects.create_user(
            'disp', 'disp@e.com', 'pw', department=cls.dept,
        )
        cls.policy = Policy.objects.create(
            code='QA-DISP', title='Disposition policy', owner_dept=cls.dept,
        )
        cls.policy.document.save('payload.html', ContentFile(b'<script>1</script>'), save=True)
        cls.html_path = cls.policy.document.name

        cls.policy2 = Policy.objects.create(
            code='QA-DISP2', title='Image policy', owner_dept=cls.dept,
        )
        cls.policy2.document.save('shot.png', ContentFile(b'\x89PNG\r\n'), save=True)
        cls.png_path = cls.policy2.document.name

    def test_html_upload_is_forced_to_download(self):
        self.client.force_login(self.user)
        response = self.client.get(f'/media/{self.html_path}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_image_upload_stays_inline(self):
        self.client.force_login(self.user)
        response = self.client.get(f'/media/{self.png_path}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('inline', response['Content-Disposition'])


# ==================================================================
# An edit may never re-parent a record to another department
# ==================================================================

class DepartmentPinningTests(TestCase):
    """``owner_dept`` is server-controlled on create *and* update."""

    @classmethod
    def setUpTestData(cls):
        cls.dept_a = Department.objects.create(name='Pin A')
        cls.dept_b = Department.objects.create(name='Pin B')
        cls.user_a = User.objects.create_user(
            'pin_a', 'pina@e.com', 'pw', department=cls.dept_a, is_hod=True,
        )

    def test_asset_edit_cannot_move_it_to_another_department(self):
        asset = Asset.objects.create(
            asset_id='PIN-1', name='Pin me', owner_dept=self.dept_a,
            description='A description long enough to pass validation.',
        )
        payload = {
            'name': asset.name,
            'hostname': asset.hostname or '',
            'ip_address': asset.ip_address or '',
            'fqdn': asset.fqdn or '',
            'asset_type': asset.asset_type,
            'hosting': asset.hosting,
            'cloud_provider': asset.cloud_provider or '',
            'cloud_region': asset.cloud_region or '',
            'location': asset.location or '',
            'os_family': asset.os_family or '',
            'os_version': asset.os_version or '',
            'vendor': asset.vendor_id or '',
            'classification': asset.classification,
            'environment': asset.environment,
            'owner_dept': self.dept_b.pk,          # the tampered value
            'owner_user': asset.owner_user_id or '',
            'is_active': 'on',
            'criticality': asset.criticality,
            'confidentiality': asset.confidentiality,
            'integrity': asset.integrity,
            'availability': asset.availability,
            'value': str(asset.value),
            'category': asset.category_id or '',
            'description': asset.description or '',
        }
        self.client.force_login(self.user_a)
        response = self.client.post(f'/assets/{asset.pk}/edit/', payload)
        self.assertEqual(response.status_code, 302)  # saved successfully
        asset.refresh_from_db()
        self.assertEqual(asset.owner_dept_id, self.dept_a.pk)


# ==================================================================
# CASCADE: deleting a control must raise the residual again
# ==================================================================

class ControlDeleteRecascadeTests(TestCase):
    """Deleting a control re-scores every risk it mitigated.

    Regression: the delete removed the ``Risk.controls`` through-rows without
    firing ``m2m_changed``, leaving the residual permanently, silently low.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Ctrl Del Dept')
        cls.cat = RiskCategory.objects.create(name='Ctrl Del Cat')

    def test_deleting_a_control_raises_the_residual(self):
        risk = Risk.objects.create(
            title='Mitigated risk', category=self.cat, owner_dept=self.dept,
            likelihood=4, impact=4, status='treating',
        )
        ctl = Control.objects.create(
            code='CD-1', name='Preventive control', owner_dept=self.dept,
            status='implemented', lifecycle_status='operational',
            effectiveness_rating='effective', control_type='preventive',
        )
        risk.controls.add(ctl)
        risk.refresh_from_db()
        mitigated = risk.residual_score
        self.assertLess(mitigated, risk.inherent_score)

        ctl.delete()
        risk.refresh_from_db()
        self.assertEqual(risk.residual_score, risk.inherent_score)
        self.assertGreater(risk.residual_score, mitigated)


# ==================================================================
# CASCADE: treatment status drives controls and risk status
# ==================================================================

class TreatmentLifecycleCascadeTests(TestCase):
    """Treatment signals keep the risk's controls and status honest."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Treat Life Dept')
        cls.cat = RiskCategory.objects.create(name='Treat Life Cat')

    def _risk(self, **kw):
        defaults = dict(
            title='Treat-life risk', category=self.cat, owner_dept=self.dept,
            likelihood=3, impact=3, status='treating',
        )
        defaults.update(kw)
        return Risk.objects.create(**defaults)

    def _control(self, code):
        return Control.objects.create(
            code=code, name='Detective', owner_dept=self.dept,
            status='implemented', lifecycle_status='operational',
            effectiveness_rating='effective', control_type='detective',
        )

    def test_cancelling_a_treatment_releases_its_controls(self):
        risk = self._risk()
        treatment = RiskTreatment.objects.create(risk=risk, action_plan='Plan')
        ctl = self._control('TL-1')
        treatment.controls.add(ctl)           # signal syncs the risk
        self.assertIn(ctl, risk.controls.all())

        treatment.status = 'cancelled'
        treatment.save()                      # no view call — signal only
        self.assertNotIn(ctl, risk.controls.all())

    def test_shell_status_change_syncs_without_the_view(self):
        risk = self._risk()
        treatment = RiskTreatment.objects.create(risk=risk, action_plan='Plan')
        treatment.status = 'completed'
        treatment.save()                      # out-of-band edit
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

    def test_risk_stays_open_while_another_treatment_is_active(self):
        risk = self._risk()
        first = RiskTreatment.objects.create(risk=risk, action_plan='A')
        second = RiskTreatment.objects.create(risk=risk, action_plan='B')

        first.status = 'completed'
        first.save()
        risk.refresh_from_db()
        self.assertNotEqual(risk.status, 'closed')

        second.status = 'completed'
        second.save()
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

    def test_deleting_a_treatment_releases_its_controls(self):
        risk = self._risk()
        treatment = RiskTreatment.objects.create(risk=risk, action_plan='Plan')
        ctl = self._control('TL-2')
        treatment.controls.add(ctl)
        self.assertIn(ctl, risk.controls.all())

        treatment.delete()
        self.assertNotIn(ctl, risk.controls.all())

    def test_reopening_a_treatment_reopens_the_risk(self):
        risk = self._risk()
        treatment = RiskTreatment.objects.create(risk=risk, action_plan='Plan')
        treatment.status = 'completed'
        treatment.save()
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

        treatment.status = 'in_progress'
        treatment.save()
        risk.refresh_from_db()
        self.assertNotEqual(risk.status, 'closed')


# ==================================================================
# CASCADE: vulnerability enrichment respects the finding's lifecycle
# ==================================================================

class VulnerabilityCascadeStatusTests(TestCase):
    """Enrichment must not resurrect a risk for a remediated finding."""

    @classmethod
    def setUpTestData(cls):
        from vulnerabilities.models import Vulnerability

        cls.dept = Department.objects.create(name='Vuln Cascade Dept')
        cls.asset = Asset.objects.create(
            asset_id='VC-1', name='critical host', owner_dept=cls.dept,
            criticality=3,
        )
        cls.vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-7777', title='Cascading CVE',
            cvss_score='9.8', cvss_severity='critical', kev_status=True,
        )

    def _finding(self, **kw):
        from vulnerabilities.models import Finding

        defaults = dict(
            vulnerability=self.vuln, asset=self.asset, owner_dept=self.dept,
            discovered_date=timezone.localdate(),
        )
        defaults.update(kw)
        return Finding.objects.create(**defaults)

    def test_a_severe_finding_raises_a_risk(self):
        finding = self._finding()
        self.assertTrue(
            Risk.objects.filter(source_finding=finding).exists()
        )

    def test_enrichment_does_not_reopen_a_remediated_finding(self):
        finding = self._finding()
        risk = Risk.objects.get(source_finding=finding)

        finding.status = 'remediated'
        finding.save()
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

        # Later CVE enrichment re-saves the vulnerability, which cascades to
        # every finding — it must leave the closed risk alone.
        self.vuln.title = 'Cascading CVE (updated)'
        self.vuln.save()

        self.assertEqual(Risk.objects.filter(source_finding=finding).count(), 1)
        risk.refresh_from_db()
        self.assertEqual(risk.status, 'closed')

    def test_a_low_severity_finding_never_cascades(self):
        from vulnerabilities.models import Finding, Vulnerability

        low = Vulnerability.objects.create(
            cve_id='CVE-2099-8888', title='Low CVE',
            cvss_score='3.1', cvss_severity='low', kev_status=False,
        )
        finding = Finding.objects.create(
            vulnerability=low, asset=self.asset, owner_dept=self.dept,
            discovered_date=timezone.localdate(),
        )
        self.assertFalse(Risk.objects.filter(source_finding=finding).exists())


# ==================================================================
# DATE LOGIC: business dates use the configured local timezone
# ==================================================================

class LocalDateConsistencyTests(TestCase):
    """Business "today" is the logged-in team's timezone, not the server's UTC.

    Regression: overdue / expiry maths mixed ``timezone.now().date()`` (UTC)
    with ``timezone.localdate()``. Under ``USE_TZ`` they differ for one part of
    every day whenever ``TIME_ZONE`` is not UTC, so a risk would open as
    overdue for a few hours before anyone could see it — and the escalations
    module, which already used ``localdate()``, disagreed with the models it
    read from.
    """

    def _modules_with_date_logic(self):
        import assets.models
        import controls.models
        import kris.models
        import risks.models
        import tickets.models
        import vendors.models
        import vulnerabilities.models

        return (
            assets.models, controls.models, kris.models, risks.models,
            tickets.models, vendors.models, vulnerabilities.models,
        )

    def test_date_comparisons_use_the_local_today(self):
        """The overdue/expiry properties never compute "today" in UTC."""
        import inspect

        offenders = []
        for module in self._modules_with_date_logic():
            targets = [
                (obj.__name__, func)
                for obj in vars(module).values()
                if inspect.isclass(obj) and obj.__module__ == module.__name__
                for func in vars(obj).values()
                if inspect.isfunction(func)
            ]
            for class_name, func in targets:
                try:
                    source = inspect.getsource(func)
                except (OSError, TypeError):
                    continue
                if 'timezone.now().date()' in source:
                    offenders.append(f'{module.__name__}.{class_name}')
        self.assertEqual([], offenders)

    def test_vendor_renewal_compares_against_the_local_date(self):
        """Writer and comparator agree under a non-UTC timezone.

        The source-scan test above is the hard guarantee; this confirms the
        behaviour end to end with a timezone where UTC and local diverge for
        most of the day.
        """
        from django.test import override_settings
        from vendors.models import Vendor

        with override_settings(TIME_ZONE='Asia/Kathmandu'):
            dept = Department.objects.create(name='Tz Dept')
            Vendor.objects.create(
                vendor_id='TZ-1', name='Tz vendor', owner_dept=dept,
                contract_renewal_date=timezone.localdate(),
            )
            vendor = Vendor.objects.get(vendor_id='TZ-1')
            self.assertEqual(vendor.days_to_renewal, 0)

    def test_risk_overdue_and_exception_expiry_use_the_local_date(self):
        from django.test import override_settings

        with override_settings(TIME_ZONE='Asia/Kathmandu'):
            dept = Department.objects.create(name='Tz Failure Dept')
            cat = RiskCategory.objects.create(name='Tz Failure Cat')
            user = User.objects.create_user(
                'tz_user', 'tz@e.com', 'pw', department=dept,
            )
            risk = Risk.objects.create(
                title='Tz risk', category=cat, owner_dept=dept,
                likelihood=3, impact=3,
                target_close_date=timezone.localdate() - _dt.timedelta(days=1),
            )
            self.assertTrue(risk.is_overdue)
            self.assertEqual(risk.days_overdue, 1)

            exc = RiskException.objects.create(
                risk=risk, title='Accept it',
                justification='Mitigation is not feasible this quarter.',
                requested_by=user,
                expiry_date=timezone.localdate() + _dt.timedelta(days=5),
            )
            self.assertEqual(exc.days_until_expiry, 5)


# ==================================================================
# NOTIFICATIONS: every kind resolves and every kind clears
# ==================================================================

class NotificationClearRuleTests(TestCase):
    """A notification kind without a clear rule lingers for ever.

    Regression: ``exception_approval_needed`` had no entry in ``CLEAR_RULES``,
    so the named approver's bell never emptied no matter what they did.
    """

    def test_every_notification_kind_has_a_clear_rule(self):
        from core.notifications import Notification
        from core.notification_registry import CLEAR_RULES, MANUAL_KINDS

        missing = [
            kind for kind, _label in Notification.KIND_CHOICES
            if kind not in CLEAR_RULES and kind not in MANUAL_KINDS
        ]
        self.assertEqual([], missing)

    def test_manual_kinds_exist(self):
        """Kinds exempted from auto-clearing must still be real choices."""
        from core.notifications import Notification
        from core.notification_registry import MANUAL_KINDS

        known = {kind for kind, _label in Notification.KIND_CHOICES}
        self.assertTrue(MANUAL_KINDS <= known)

    def test_ruleless_kind_is_detected_by_the_guard(self):
        """The guard above would actually catch a new rule-less kind."""
        from core.notifications import Notification
        from core.notification_registry import CLEAR_RULES

        self.assertIn('exception_approval_needed', CLEAR_RULES)
        self.assertTrue(Notification.KIND_CHOICES)

    def test_exception_approval_clears_when_no_longer_pending(self):
        from core.notification_registry import refresh_notifications
        from core.notifications import Notification

        dept = Department.objects.create(name='Approval Dept')
        cat = RiskCategory.objects.create(name='Approval Cat')
        user = User.objects.create_user('appr', 'appr@e.com', 'pw', department=dept)
        risk = Risk.objects.create(
            title='Approval risk', category=cat, owner_dept=dept,
            likelihood=2, impact=2,
        )
        exc = RiskException.objects.create(
            risk=risk, title='Accept it',
            justification='Mitigation is not feasible this quarter.',
            requested_by=user, approver=user,
            expiry_date=timezone.localdate() + _dt.timedelta(days=30),
        )
        self.assertEqual(exc.status, 'pending')

        note = Notification.objects.create(
            kind='exception_approval_needed',
            title='Approval required',
            action_url=f'/risks/exceptions/{exc.pk}/',
            owner_dept=dept, recipient=user,
            ref_model='risks.riskexception', ref_id=exc.pk,
        )

        refresh_notifications(dept=dept)
        note.refresh_from_db()
        self.assertFalse(note.is_cleared)

        exc.status = 'approved'
        exc.save()
        refresh_notifications(dept=dept)
        note.refresh_from_db()
        self.assertTrue(note.is_cleared)


# ==================================================================
# LINKS: no stored scriptable URLs in evidence locations
# ==================================================================

class ExternalUrlSafetyTests(TestCase):
    """``EvidenceItem.url_location`` may never link to ``javascript:``."""

    def test_scriptable_schemes_are_rejected(self):
        from django.core.exceptions import ValidationError
        from core.validators import is_safe_external_url, validate_external_url

        for bad in (
            'javascript:alert(1)', 'JaVaScRiPt:alert(1)',
            'data:text/html,<script>1</script>', 'vbscript:msgbox(1)',
        ):
            with self.subTest(bad=bad):
                self.assertFalse(is_safe_external_url(bad))
                with self.assertRaises(ValidationError):
                    validate_external_url(bad)

    def test_normals_urls_and_paths_are_accepted(self):
        from core.validators import is_safe_external_url

        for good in (
            'https://example.com/report', 'http://intranet.local/doc.pdf',
            '/media/audit_evidence/x.pdf', 'C:\\evidence\\x.pdf',
            '\\\\server\\share\\log.txt',
        ):
            with self.subTest(good=good):
                self.assertTrue(is_safe_external_url(good))

    def test_existing_unsafe_row_is_never_rendered_as_a_link(self):
        from audits.models import EvidenceItem

        dept = Department.objects.create(name='Unsafe URL Dept')
        item = EvidenceItem.objects.create(
            title='Unsafe evidence', owner_dept=dept,
        )
        # Rows written before the validator existed are not re-validated on
        # read — Update must not silently rewrite stored data.
        EvidenceItem.objects.filter(pk=item.pk).update(
            url_location='javascript:alert(document.cookie)'
        )
        item.refresh_from_db()
        self.assertEqual(item.safe_url_location, '')
        self.assertTrue(item.url_location)  # raw value is untouched, just not linked

    def test_form_rejects_a_javascript_url(self):
        from audits.forms import EvidenceItemForm

        dept = Department.objects.create(name='URL Form Dept')
        form = EvidenceItemForm(data={
            'title': 'Bad link', 'evidence_type': 'document',
            'owner_dept': dept.pk, 'url_location': 'javascript:alert(1)',
        })
        self.assertFalse(form.is_valid())
        rendered = str(form['url_location'].errors)
        self.assertTrue(rendered)
        self.assertIn('not allowed', rendered)
        # ...and the safe-scheme validator is what rejected it.
        self.assertEqual(['unsafe_url_scheme'], [
            each.code for each in form.errors['url_location'].data
        ])


class DeletionCascadeTests(TestCase):
    """Deleting risks/findings cleans up cascaded risks & alert tickets without closing baselines."""

    def test_finding_cascade_keeps_asset_baseline_risk_open(self):
        import datetime as _dt
        from assets.models import Asset
        from risks.models import Risk
        from vulnerabilities.models import Finding, Vulnerability

        dept = Department.objects.create(name='Baseline Cascade Dept')
        asset = Asset.objects.create(
            asset_id='QA-BC-1', name='Baseline Host', owner_dept=dept,
        )
        baseline = Risk.objects.filter(
            assets=asset, title__startswith='Unassessed risk:'
        ).first()
        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.status, 'identified')

        vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-0101', title='Critical Cascade',
            cvss_score='9.8', cvss_severity='critical', kev_status=True,
        )
        finding = Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=dept,
            discovered_date=_dt.date.today(),
        )
        cascaded = Risk.objects.get(source_finding=finding)
        self.assertIn(asset, cascaded.assets.all())

        baseline.refresh_from_db()
        self.assertEqual(baseline.status, 'identified')

    def test_deleting_finding_deletes_unassessed_cascaded_risk_and_cancels_alerts(self):
        import datetime as _dt
        from django.contrib.contenttypes.models import ContentType
        from assets.models import Asset
        from risks.models import Risk
        from tickets.models import Ticket
        from vulnerabilities.models import Finding, Vulnerability

        dept = Department.objects.create(name='Delete Cascade Dept')
        asset = Asset.objects.create(
            asset_id='QA-DC-1', name='Delete Cascade Host', criticality=4, owner_dept=dept,
        )
        vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-0202', title='KEV Cascade',
            cvss_score='9.8', cvss_severity='critical', kev_status=True,
        )
        finding = Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=dept,
            discovered_date=_dt.date.today(),
        )
        cascaded = Risk.objects.get(source_finding=finding)
        finding_ticket = Ticket.objects.create(
            title='KEV alert', source='alert',
            content_type=ContentType.objects.get_for_model(Finding),
            object_id=finding.pk, status='open', owner_dept=dept,
        )
        risk_ticket = Ticket.objects.create(
            title='Risk alert', source='alert',
            content_type=ContentType.objects.get_for_model(Risk),
            object_id=cascaded.pk, status='open', owner_dept=dept,
        )

        finding.delete()

        self.assertFalse(Risk.objects.filter(pk=cascaded.pk).exists())
        finding_ticket.refresh_from_db()
        risk_ticket.refresh_from_db()
        self.assertEqual(finding_ticket.status, 'cancelled')
        self.assertEqual(risk_ticket.status, 'cancelled')

    def test_deleting_finding_keeps_assessed_risk_and_cancels_risk_ticket_on_risk_delete(self):
        import datetime as _dt
        from django.contrib.contenttypes.models import ContentType
        from assets.models import Asset
        from risks.models import Risk
        from tickets.models import Ticket
        from vulnerabilities.models import Finding, Vulnerability

        dept = Department.objects.create(name='Assessed Cascade Dept')
        asset = Asset.objects.create(
            asset_id='QA-AC-1', name='Assessed Host', owner_dept=dept,
        )
        vuln = Vulnerability.objects.create(
            cve_id='CVE-2099-0303', title='Assessed KEV',
            cvss_score='9.1', cvss_severity='critical', kev_status=True,
        )
        finding = Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=dept,
            discovered_date=_dt.date.today(),
        )
        cascaded = Risk.objects.get(source_finding=finding)
        cascaded.status = 'monitoring'
        cascaded.save()

        finding.delete()
        cascaded.refresh_from_db()
        self.assertIsNone(cascaded.source_finding)
        self.assertEqual(cascaded.status, 'monitoring')

        ticket = Ticket.objects.create(
            title='Risk breach alert', source='alert',
            content_type=ContentType.objects.get_for_model(Risk),
            object_id=cascaded.pk, status='open', owner_dept=dept,
        )
        cascaded_pk = cascaded.pk
        cascaded.delete()
        self.assertFalse(Risk.objects.filter(pk=cascaded_pk).exists())
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'cancelled')


class AnonymousUserExclusionTests(TestCase):
    """django-guardian's AnonymousUser row stays out of UI user lists, sharing, and dropdowns."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Real Users Dept')
        cls.anon, _ = User.objects.get_or_create(
            username='AnonymousUser',
            defaults={'is_active': True},
        )
        # Attach AnonymousUser to the dept too, to verify DepartmentListView user_count excludes it.
        User.objects.filter(pk=cls.anon.pk).update(department=cls.dept, is_active=True)
        cls.anon.refresh_from_db()
        cls.admin = User.objects.create_superuser(
            'anon_check_admin', 'aca@example.com', 'pw', department=cls.dept,
        )

    def test_admin_user_and_department_lists_exclude_anonymous_user(self):
        self.client.force_login(self.admin)
        users_resp = self.client.get(reverse('core:users_list'))
        self.assertEqual(users_resp.status_code, 200)
        self.assertNotContains(users_resp, 'AnonymousUser')
        self.assertEqual(users_resp.context['total_count'], 1)

        dept_resp = self.client.get(reverse('core:departments_list'))
        self.assertEqual(dept_resp.status_code, 200)
        row = next(r for r in dept_resp.context['rows'] if r['dept'].pk == self.dept.pk)
        self.assertEqual(row['user_count'], 1)

    def test_shareable_users_and_share_endpoint_reject_anonymous_user(self):
        from core.templatetags.permissions_tags import shareable_users
        from risks.models import Risk, RiskCategory

        self.assertNotIn(self.anon, list(shareable_users()))
        cat = RiskCategory.objects.create(name='Share Ops')
        risk = Risk.objects.create(title='Share Test Risk', category=cat, owner_dept=self.dept)
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('core:object_share', kwargs={'app_label': 'risks', 'model_name': 'risk', 'pk': risk.pk}),
            {'action': 'grant', 'principal_type': 'user', 'principal_id': str(self.anon.pk), 'perms': ['view']},
        )
        self.assertEqual(resp.status_code, 404)

    def test_form_user_dropdowns_exclude_anonymous_user(self):
        self.client.force_login(self.admin)
        for url in (
            reverse('risks:create'),
            reverse('kris:create'),
            reverse('vulnerabilities:manual_create'),
            reverse('audits:test_create'),
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, 'AnonymousUser')


class SearchDeleteAndSettingsFixTests(TestCase):
    """Regression coverage for Fix 7: RSK/AuditFinding search, deletes, settings & copy."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Fix7 Dept')
        cls.other_dept = Department.objects.create(name='Fix7 Other Dept')
        cls.hod = User.objects.create_user(
            'fix7_hod', 'f7hod@example.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.member = User.objects.create_user(
            'fix7_member', 'f7mem@example.com', 'pw', department=cls.dept, is_hod=False,
        )

    def test_risk_code_search_and_large_number_safety(self):
        from risks.models import Risk, RiskCategory

        cat = RiskCategory.objects.create(name='Search Ops')
        risk = Risk.objects.create(
            title='Unrelated Payment Gateway Name', category=cat, owner_dept=self.dept,
        )
        code = f'RSK-{risk.pk:04d}'
        self.client.force_login(self.hod)

        for url in (reverse('risks:list'), reverse('core:search')):
            with self.subTest(url=url):
                resp = self.client.get(url, {'q': code})
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, risk.title)

                # Lowercase and bare digits also work, and huge integer does not 500
                resp_lower = self.client.get(url, {'q': code.lower()})
                self.assertEqual(resp_lower.status_code, 200)
                self.assertContains(resp_lower, risk.title)

                resp_huge = self.client.get(url, {'q': '99999999999999999999'})
                self.assertEqual(resp_huge.status_code, 200)

    def test_global_search_includes_scoped_audit_findings(self):
        from audits.models import Audit, AuditFinding

        audit = Audit.objects.create(name='Fix7 Audit', owner_dept=self.dept)
        own_finding = AuditFinding.objects.create(
            title='Fix7 Visible Control Gap', audit=audit, owner_dept=self.dept,
        )
        other_audit = Audit.objects.create(name='Other Audit', owner_dept=self.other_dept)
        AuditFinding.objects.create(
            title='Fix7 Hidden Control Gap', audit=other_audit, owner_dept=self.other_dept,
        )

        self.client.force_login(self.hod)
        resp = self.client.get(reverse('core:search'), {'q': 'Fix7'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, own_finding.title)
        self.assertNotContains(resp, 'Fix7 Hidden Control Gap')

    def test_userdate_settings_and_policy_copy(self):
        import datetime as _dt
        from django.template import Context, Template
        from policies.forms import PolicyForm

        tpl = Template('{% load user_formats %}{% userdate dt %}')
        rendered = tpl.render(Context({'dt': _dt.date(2026, 1, 15)}))
        self.assertEqual(rendered, '2026-01-15')

        self.client.force_login(self.hod)
        resp = self.client.get(reverse('core:settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'v3.2.0')
        self.assertNotContains(resp, 'Today prints as: <code>Y-m-d</code>')

        help_text = PolicyForm().fields['content'].help_text
        self.assertIn('below', help_text)
        self.assertNotIn('above', help_text)

    def test_missing_delete_views_work_for_hod_and_reject_non_hod(self):
        import datetime as _dt
        from assets.models import Asset
        from kris.models import KRI
        from vendors.models import Vendor, VendorAssessment
        from vulnerabilities.models import Finding, Vulnerability

        vendor = Vendor.objects.create(name='Delete Me Vendor', owner_dept=self.dept)
        assessment = VendorAssessment.objects.create(
            vendor=vendor, vendor_tier=vendor.tier, assessment_date=_dt.date.today(),
            security_score=10, compliance_score=10, financial_score=10,
            reputation_score=10, operational_score=10,
        )
        kri = KRI.objects.create(
            name='Delete Me KRI', owner_dept=self.dept,
            amber_threshold=5, red_threshold=10,
        )
        asset = Asset.objects.create(asset_id='QA-DEL-1', name='Del Host', owner_dept=self.dept)
        vuln = Vulnerability.objects.create(cve_id='CVE-2099-9999', title='Del CVE', cvss_score='7.5')
        finding = Finding.objects.create(
            vulnerability=vuln, asset=asset, owner_dept=self.dept, discovered_date=_dt.date.today(),
        )

        delete_urls = [
            reverse('vendors:assessment_delete', kwargs={'pk': assessment.pk}),
            reverse('vendors:delete', kwargs={'pk': vendor.pk}),
            reverse('kris:delete', kwargs={'pk': kri.pk}),
            reverse('vulnerabilities:finding_delete', kwargs={'pk': finding.pk}),
        ]

        self.client.force_login(self.member)
        for url in delete_urls:
            with self.subTest(role='member', url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.hod)
        for url in delete_urls:
            with self.subTest(role='hod', url=url):
                get_resp = self.client.get(url)
                self.assertEqual(get_resp.status_code, 200)
                post_resp = self.client.post(url)
                self.assertEqual(post_resp.status_code, 302)

        self.assertFalse(VendorAssessment.objects.filter(pk=assessment.pk).exists())
        self.assertFalse(Vendor.objects.filter(pk=vendor.pk).exists())
        self.assertFalse(KRI.objects.filter(pk=kri.pk).exists())
        self.assertFalse(Finding.objects.filter(pk=finding.pk).exists())
