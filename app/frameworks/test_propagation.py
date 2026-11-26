"""Cross-framework propagation: one mapping proposes its equivalents elsewhere."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from controls.models import Control, ControlFrameworkMapping
from core.models import Department
from frameworks.models import Framework, FrameworkControl
from frameworks.propagation import AUTO_PREFIX, link, paused


class PropagationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT')
        cls.iso = Framework.objects.create(name='ISO/IEC 27001', version='2022')
        cls.nist = Framework.objects.create(name='NIST CSF', version='2.0')
        cls.control = Control.objects.create(
            code='CTL-BAK-001', name='Backup and restore', owner_dept=cls.dept,
        )
        cls.iso_backup = FrameworkControl.objects.create(
            framework=cls.iso, code='A.8.13', title='Information backup',
        )
        cls.iso_backup_test = FrameworkControl.objects.create(
            framework=cls.iso, code='A.8.14', title='Backup restoration testing',
        )
        cls.nist_backup = FrameworkControl.objects.create(
            framework=cls.nist, code='PR.DS-11',
            title='Backups of data are created, protected, maintained, and tested',
        )
        cls.nist_encrypt = FrameworkControl.objects.create(
            framework=cls.nist, code='PR.DS-01',
            title='Data at rest is encrypted',
        )

    def test_mapping_proposes_the_same_topic_in_another_framework(self):
        mapping = ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.iso_backup,
        )

        auto = ControlFrameworkMapping.objects.get(
            control=self.control, framework_control=self.nist_backup,
        )
        self.assertEqual(auto.relationship, 'intersects')
        self.assertTrue(auto.notes.startswith(AUTO_PREFIX))
        self.assertIn('A.8.13', auto.notes)
        self.assertEqual(mapping.auto_linked_count, 1)

    def test_it_never_links_within_the_same_framework(self):
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.iso_backup,
        )

        self.assertFalse(ControlFrameworkMapping.objects.filter(
            control=self.control, framework_control=self.iso_backup_test,
        ).exists())

    def test_running_again_does_not_duplicate_the_proposal(self):
        mapping = ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.iso_backup,
        )

        self.assertEqual(link(self.control, self.iso_backup), 0)
        self.assertEqual(mapping.control.framework_mappings.count(), 2)

    def test_paused_suppresses_propagation(self):
        with paused():
            ControlFrameworkMapping.objects.create(
                control=self.control, framework_control=self.iso_backup,
            )

        self.assertEqual(self.control.framework_mappings.count(), 1)

    def test_an_unrelated_topic_is_not_linked(self):
        crypto = FrameworkControl.objects.create(
            framework=self.iso, code='A.8.24', title='Use of cryptography',
        )
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=crypto,
        )

        self.assertFalse(ControlFrameworkMapping.objects.filter(
            control=self.control, framework_control=self.nist_backup,
        ).exists())

    def test_adding_to_the_legacy_m2m_proposes_equivalents(self):
        self.control.framework_controls.add(self.iso_backup)

        self.assertTrue(ControlFrameworkMapping.objects.filter(
            control=self.control, framework_control=self.nist_backup,
        ).exists())


class BackfillCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT')
        cls.iso = Framework.objects.create(name='ISO/IEC 27001', version='2022')
        cls.nist = Framework.objects.create(name='NIST CSF', version='2.0')
        cls.control = Control.objects.create(
            code='CTL-BAK-001', name='Backup and restore', owner_dept=cls.dept,
        )
        cls.iso_backup = FrameworkControl.objects.create(
            framework=cls.iso, code='A.8.13', title='Information backup',
        )
        cls.nist_backup = FrameworkControl.objects.create(
            framework=cls.nist, code='PR.DS-11',
            title='Backups of data are created, protected, maintained, and tested',
        )
        with paused():
            ControlFrameworkMapping.objects.create(
                control=cls.control, framework_control=cls.iso_backup,
            )

    def test_dry_run_writes_nothing(self):
        call_command('propagate_framework_mappings', '--dry-run', stdout=StringIO())

        self.assertEqual(self.control.framework_mappings.count(), 1)

    def test_backfill_creates_the_proposals(self):
        call_command('propagate_framework_mappings', stdout=StringIO())

        self.assertTrue(ControlFrameworkMapping.objects.filter(
            control=self.control, framework_control=self.nist_backup,
        ).exists())
