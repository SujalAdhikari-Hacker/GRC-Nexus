"""Excel round-trip tests: export, create, update, partial rows, scoping."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from core.models import Department, User
from risks.models import Risk, RiskCategory

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
