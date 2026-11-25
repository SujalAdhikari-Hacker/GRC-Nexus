"""The NRB catalogues are data files, so the tests guard the data as much as the command."""
import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from frameworks.models import Framework, FrameworkControl
from frameworks.management.commands.seed_nrb_frameworks import DATA_DIR

EXPECTED = {
    'NRB Cyber Resilience Guidelines': 185,
    'NRB Artificial Intelligence Guidelines': 61,
    'Nepal Digital & Electronic Acts': 27,
    'NRB IT & Cyber Security Directives': 13,
}


class SeedNrbFrameworksTests(TestCase):
    def seed(self):
        call_command('seed_nrb_frameworks', stdout=StringIO())

    def test_seeding_creates_every_framework_with_its_requirements(self):
        self.seed()

        for name, count in EXPECTED.items():
            framework = Framework.objects.get(name=name)
            self.assertEqual(framework.controls.count(), count, name)

    def test_running_again_updates_instead_of_duplicating(self):
        self.seed()
        self.seed()

        self.assertEqual(Framework.objects.count(), len(EXPECTED))
        self.assertEqual(FrameworkControl.objects.count(), sum(EXPECTED.values()))

    def test_every_catalogue_entry_fits_the_model_and_has_a_unique_code(self):
        for path in DATA_DIR.glob('*.json'):
            requirements = json.loads(path.read_text(encoding='utf-8'))
            codes = [item['code'] for item in requirements]
            self.assertEqual(len(codes), len(set(codes)), path.name)
            for item in requirements:
                self.assertLessEqual(len(item['title']), 300, item['code'])
                self.assertTrue(item['title'].strip(), item['code'])

    def test_the_acts_and_directives_are_labelled_as_curated_summaries(self):
        self.seed()

        for name in ('Nepal Digital & Electronic Acts', 'NRB IT & Cyber Security Directives'):
            framework = Framework.objects.get(name=name)
            self.assertIn('Curated summary', framework.description)

    def test_the_acts_framework_names_the_three_acts(self):
        self.seed()

        framework = Framework.objects.get(name='Nepal Digital & Electronic Acts')
        self.assertTrue(framework.controls.filter(code__startswith='NEPAL-ETA-').exists())
        self.assertTrue(framework.controls.filter(code__startswith='NEPAL-ETR-').exists())
        self.assertTrue(framework.controls.filter(code__startswith='NEPAL-IPA-').exists())
