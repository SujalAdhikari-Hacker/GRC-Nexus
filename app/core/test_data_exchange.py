"""Excel round-trip tests: export, create, update, partial rows, scoping."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from assets.models import Asset, AssetCategory
from core.models import Department, User
from incidents.models import Incident
from risks.models import Risk, RiskCategory, RiskTreatment
from tickets.models import Ticket
from vulnerabilities.models import Finding, Vulnerability

HEADERS = ['ID', 'Title', 'Category', 'Department', 'Likelihood (1-5)', 'Impact (1-5)']


def workbook(headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Data'
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def uploaded(content, name='data.xlsx'):
    return SimpleUploadedFile(
        name, content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


class DataExchangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT')
        cls.other_dept = Department.objects.create(name='Finance')
        cls.user = User.objects.create_user(
            'importer', 'importer@example.com', 'pw',
            department=cls.dept, is_hod=True,
        )
        cls.category = RiskCategory.objects.create(name='Cyber')
        cls.risk = Risk.objects.create(
            title='Phishing risk', category=cls.category,
            owner_dept=cls.dept, likelihood=3, impact=4,
        )

    def post_rows(self, rows, headers=HEADERS):
        self.client.force_login(self.user)
        return self.client.post(reverse('core:data_exchange'), {
            'entity': 'risks',
            'file': uploaded(workbook(headers, rows)),
        })

    def post_file(self, entity, content, name='data.xlsx'):
        self.client.force_login(self.user)
        return self.client.post(reverse('core:data_exchange'), {
            'entity': entity,
            'file': uploaded(content, name),
        })

    def test_signing_in_is_required(self):
        response = self.client.get(reverse('core:data_exchange'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_export_contains_the_rows_the_user_may_see(self):
        Risk.objects.create(
            title='Finance only', category=self.category,
            owner_dept=self.other_dept, likelihood=2, impact=2,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('core:data_export', args=['risks'])
        )

        self.assertEqual(response.status_code, 200)
        book = load_workbook(BytesIO(response.content))
        sheet = book['Data']
        self.assertEqual(sheet.cell(row=1, column=1).value, 'ID')
        titles = [row[1] for row in sheet.iter_rows(min_row=2, values_only=True)]
        self.assertIn('Phishing risk', titles)
        self.assertNotIn('Finance only', titles)

    def test_a_blank_id_creates_a_risk(self):
        response = self.post_rows(
            [['', 'New supplier risk', 'Cyber', 'IT', 2, 5]]
        )

        self.assertEqual(response.context['result']['created'], 1)
        risk = Risk.objects.get(title='New supplier risk')
        self.assertEqual(risk.owner_dept, self.dept)
        self.assertEqual(risk.inherent_score, 10)

    def test_an_id_updates_the_row(self):
        response = self.post_rows(
            [[self.risk.pk, 'Phishing risk (revised)', '', '', '', '']]
        )

        self.assertEqual(response.context['result']['updated'], 1)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.title, 'Phishing risk (revised)')

    def test_a_blank_cell_leaves_the_stored_value_alone(self):
        self.post_rows([[self.risk.pk, 'Renamed', '', '', '', '']])

        self.risk.refresh_from_db()
        self.assertEqual(self.risk.impact, 4)
        self.assertEqual(self.risk.category, self.category)

    def test_a_bad_row_is_reported_and_the_good_row_still_imports(self):
        response = self.post_rows([
            ['', 'Good risk', 'Cyber', 'IT', 3, 3],
            ['', 'Bad risk', 'No Such Category', 'IT', 3, 3],
        ])

        result = response.context['result']
        self.assertEqual(result['created'], 1)
        self.assertEqual(len(result['errors']), 1)
        row_number, message = result['errors'][0]
        self.assertEqual(row_number, 3)
        self.assertIn('No Such Category', message)
        self.assertTrue(Risk.objects.filter(title='Good risk').exists())

    def test_a_user_cannot_update_another_departments_row(self):
        finance_risk = Risk.objects.create(
            title='Finance risk', category=self.category,
            owner_dept=self.other_dept, likelihood=2, impact=2,
        )

        response = self.post_rows([[finance_risk.pk, 'Hijacked', '', '', '', '']])

        self.assertEqual(response.context['result']['updated'], 0)
        finance_risk.refresh_from_db()
        self.assertEqual(finance_risk.title, 'Finance risk')

    def test_formula_like_text_round_trips_without_the_export_escape(self):
        formula_risk = Risk.objects.create(
            title='=SUM(A1)', category=self.category,
            owner_dept=self.dept, likelihood=2, impact=2,
        )
        self.client.force_login(self.user)
        export = self.client.get(reverse('core:data_export', args=['risks']))

        response = self.client.post(reverse('core:data_exchange'), {
            'entity': 'risks',
            'file': uploaded(export.content),
        })

        self.assertEqual(response.context['result']['errors'], [])
        formula_risk.refresh_from_db()
        self.assertEqual(formula_risk.title, '=SUM(A1)')

    def test_the_template_has_headers_but_no_rows(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('core:data_export', args=['risks']) + '?template=1'
        )

        sheet = load_workbook(BytesIO(response.content))['Data']
        self.assertEqual(sheet.max_row, 1)
        self.assertEqual(sheet.cell(row=1, column=1).value, 'ID')
        self.assertEqual(sheet.cell(row=1, column=2).value, 'Title')

    def test_csv_export_can_be_uploaded_back(self):
        self.client.force_login(self.user)
        export = self.client.get(
            reverse('core:data_export', args=['risks']) + '?format=csv'
        )
        self.assertIn('ID,Title', export.content.decode('utf-8-sig'))

        response = self.post_file('risks', export.content, 'risks.csv')

        result = response.context['result']
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['errors'], [])

    def test_csv_upload_creates_a_risk(self):
        content = (
            'ID,Title,Category,Department,Likelihood (1-5),Impact (1-5)\n'
            ',CSV risk,Cyber,IT,4,5\n'
        ).encode('utf-8')

        response = self.post_file('risks', content, 'risks.csv')

        self.assertEqual(response.context['result']['created'], 1)
        self.assertTrue(Risk.objects.filter(title='CSV risk').exists())

    def test_asset_upload_creates_an_asset(self):
        AssetCategory.objects.create(name='Server')
        headers = [
            'ID', 'Name', 'Description', 'Type', 'Department',
            'Asset Category', 'Criticality (1-4)',
        ]

        response = self.post_file('assets', workbook(headers, [
            ['', 'Payments API', 'Public payments API server', 'software', 'IT', 'Server', 3],
        ]), 'assets.xlsx')

        self.assertEqual(response.context['result']['created'], 1)
        asset = Asset.objects.get(name='Payments API')
        self.assertEqual(asset.owner_dept, self.dept)
        self.assertEqual(asset.criticality, 3)

    def test_incident_upload_numbers_its_own_reference(self):
        headers = ['ID', 'Title', 'Description', 'Department', 'Detected At']

        response = self.post_file('incidents', workbook(headers, [
            ['', 'Phishing wave', 'Reported by staff', 'IT', '2026-01-02 10:30'],
        ]), 'incidents.xlsx')

        self.assertEqual(response.context['result']['created'], 1)
        incident = Incident.objects.get(title='Phishing wave')
        self.assertTrue(incident.reference.startswith('INC-'))
        self.assertEqual(incident.detected_at.year, 2026)

    def test_pdf_export_returns_a_pdf(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('core:data_export', args=['risks']) + '?format=pdf'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_a_non_hod_user_cannot_use_the_page(self):
        plain = User.objects.create_user(
            'plain', 'plain@example.com', 'pw', department=self.dept,
        )
        self.client.force_login(plain)

        self.assertEqual(
            self.client.get(reverse('core:data_exchange')).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse('core:data_export', args=['risks'])).status_code,
            403,
        )

    def test_risk_treatment_upload_links_the_named_risk(self):
        headers = ['ID', 'Risk', 'Action Plan', 'Status']

        response = self.post_file('treatments', workbook(headers, [
            ['', 'Phishing risk', 'Run quarterly awareness training', 'planned'],
        ]), 'treatments.xlsx')

        self.assertEqual(response.context['result']['created'], 1)
        treatment = RiskTreatment.objects.get(action_plan='Run quarterly awareness training')
        self.assertEqual(treatment.risk, self.risk)

    def test_treatment_for_another_departments_risk_is_rejected(self):
        other = Risk.objects.create(
            title='Finance risk', category=self.category,
            owner_dept=self.other_dept, likelihood=2, impact=2,
        )
        headers = ['ID', 'Risk', 'Action Plan']

        response = self.post_file('treatments', workbook(headers, [
            ['', other.title, 'Should not import'],
        ]), 'treatments.xlsx')

        result = response.context['result']
        self.assertEqual(result['created'], 0)
        self.assertTrue(result['errors'])
        self.assertFalse(RiskTreatment.objects.exists())

    def test_ticket_upload_numbers_its_own_reference(self):
        headers = ['ID', 'Title', 'Department', 'Priority (1-4)']

        response = self.post_file('tickets', workbook(headers, [
            ['', 'Patch the VPN appliance', 'IT', 1],
        ]), 'tickets.xlsx')

        self.assertEqual(response.context['result']['created'], 1)
        ticket = Ticket.objects.get(title='Patch the VPN appliance')
        self.assertTrue(ticket.ticket_id.startswith('TKT-'))
        self.assertEqual(ticket.owner_dept, self.dept)

    def test_vulnerability_finding_upload_links_asset_and_cve(self):
        asset = Asset.objects.create(
            name='Payments API', description='Public payments API server',
            owner_dept=self.dept,
        )
        vulnerability = Vulnerability.objects.create(
            cve_id='CVE-2026-0001', title='Example vulnerability',
        )
        headers = ['ID', 'CVE ID', 'Asset', 'Discovered Date']

        response = self.post_file('vulnerability-findings', workbook(headers, [
            ['', 'CVE-2026-0001', asset.name, '2026-02-03'],
        ]), 'findings.xlsx')

        self.assertEqual(response.context['result']['created'], 1)
        finding = Finding.objects.get(vulnerability=vulnerability)
        self.assertEqual(finding.asset, asset)
        self.assertEqual(finding.owner_dept, self.dept)
        self.assertIsNotNone(finding.sla_due_date)

    def test_finding_for_another_departments_asset_is_rejected(self):
        asset = Asset.objects.create(
            name='Finance ledger', description='Finance ledger server',
            owner_dept=self.other_dept,
        )
        Vulnerability.objects.create(
            cve_id='CVE-2026-0002', title='Example vulnerability',
        )
        headers = ['ID', 'CVE ID', 'Asset', 'Discovered Date']

        response = self.post_file('vulnerability-findings', workbook(headers, [
            ['', 'CVE-2026-0002', asset.name, '2026-02-03'],
        ]), 'findings.xlsx')

        result = response.context['result']
        self.assertEqual(result['created'], 0)
        self.assertTrue(result['errors'])
        self.assertFalse(Finding.objects.exists())
