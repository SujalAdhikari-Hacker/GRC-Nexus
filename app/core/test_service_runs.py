"""Service-run log: every scheduled command leaves a row behind.

The log is what makes an unattended failure visible, so the tests cover the
success path, the failure path, dry runs (not recorded), retention, and the
page that reads the rows back.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .management.base import LoggedCommand
from .models import Department, ServiceRun, User
from .service_runs import RETENTION_DAYS, record_run


class OkCommand(LoggedCommand):
    def handle(self, *args, **options):
        self.record_counts(items=3, skipped=1)
        return 'summary text'


class BoomCommand(LoggedCommand):
    def handle(self, *args, **options):
        raise CommandError('feed is down')


class DryRunCommand(LoggedCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        return 'nothing written'


class ServiceRunRecordTests(TestCase):
    def test_a_successful_run_records_status_counts_and_duration(self):
        call_command(OkCommand(), stdout=StringIO())

        run = ServiceRun.objects.get()
        self.assertEqual(run.status, 'ok')
        self.assertIsNotNone(run.finished_at)
        self.assertIsNotNone(run.duration_seconds)
        self.assertEqual(run.counts, {'items': 3, 'skipped': 1})
        self.assertEqual(run.message, '')

    def test_a_failing_run_is_recorded_and_the_error_propagates(self):
        with self.assertRaises(CommandError):
            call_command(BoomCommand(), stdout=StringIO())

        run = ServiceRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.assertIn('feed is down', run.message)
        self.assertIsNotNone(run.finished_at)

    def test_a_dry_run_leaves_no_row(self):
        call_command(DryRunCommand(), dry_run=True, stdout=StringIO())

        self.assertFalse(ServiceRun.objects.exists())

    def test_runs_older_than_the_retention_window_are_pruned(self):
        stale = ServiceRun.objects.create(service='old_service', status='ok')
        ServiceRun.objects.filter(pk=stale.pk).update(
            started_at=timezone.now() - timezone.timedelta(days=RETENTION_DAYS + 1)
        )

        call_command(OkCommand(), stdout=StringIO())

        self.assertFalse(ServiceRun.objects.filter(pk=stale.pk).exists())
        self.assertEqual(ServiceRun.objects.count(), 1)

    def test_the_escalation_sweep_is_wired_to_the_log(self):
        call_command('send_escalations', no_email=True, stdout=StringIO())

        run = ServiceRun.objects.get()
        self.assertEqual(run.service, 'send_escalations')
        self.assertEqual(run.status, 'ok')
        self.assertIn('found', run.counts)

    def test_record_run_closes_the_row_on_a_plain_exception(self):
        with self.assertRaises(RuntimeError):
            with record_run('unit_service'):
                raise RuntimeError('kaboom')

        run = ServiceRun.objects.get(service='unit_service')
        self.assertEqual(run.status, 'failed')
        self.assertIn('kaboom', run.message)


class ServiceRunPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Ops Dept')
        cls.superuser = User.objects.create_superuser(
            'runs_admin', 'runs@example.com', 'pw',
        )
        cls.hod = User.objects.create_user(
            'runs_hod', 'hod@example.com', 'pw', department=cls.dept, is_hod=True,
        )
        cls.run_row = ServiceRun.objects.create(
            service='sweep_nis2_deadlines', status='ok', counts={'scanned': 4},
        )

    def test_a_superuser_sees_the_runs_and_their_counts(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('core:service_runs'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sweep_nis2_deadlines')
        self.assertContains(response, 'scanned=4')

    def test_a_hod_is_refused(self):
        self.client.force_login(self.hod)
        self.assertEqual(
            self.client.get(reverse('core:service_runs')).status_code, 403
        )

    def test_signing_in_is_required(self):
        response = self.client.get(reverse('core:service_runs'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_the_status_filter_hides_other_runs(self):
        ServiceRun.objects.create(service='send_email_digest', status='failed')
        self.client.force_login(self.superuser)

        response = self.client.get(reverse('core:service_runs'), {'status': 'failed'})

        self.assertEqual(
            [run.service for run in response.context['runs']],
            ['send_email_digest'],
        )
