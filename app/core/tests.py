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

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from assets.models import Asset
from controls.models import Control
from core.mixins import csv_safe, scope_queryset, user_can_access
from core.models import Department, User
from core.dashboard_data import iter_month_bounds
from risks.services import calculate_residual_from_controls


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
        past = _dt.date.today() - _dt.timedelta(days=3)
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
