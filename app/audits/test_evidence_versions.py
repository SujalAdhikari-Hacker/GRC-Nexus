"""Evidence versioning: a SHA-256 worth of proof per upload.

Every upload of an evidence file is recorded once with its stored path, size
and SHA-256, and each recorded version stays downloadable after the record is
replaced. These tests cover the model hooks, the scoped download and the two
form paths.
"""
import hashlib
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Department, User

from .models import EvidenceItem

PDF = b'%PDF-1.7\nfirst version of the evidence\n'
PDF2 = b'%PDF-1.7\nsecond version, longer and different\n'


class EvidenceVersionBase(TestCase):
    @classmethod
    def setUpClass(cls):
        # MEDIA_ROOT must be overridden before super().setUpClass(), because
        # Django runs setUpTestData() inside it.
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Evidence Dept')
        cls.other_dept = Department.objects.create(name='Other Evidence Dept')
        cls.user = User.objects.create_user(
            'ev_user', 'ev@example.com', 'pw', department=cls.dept,
        )
        cls.outsider = User.objects.create_user(
            'ev_outsider', 'evo@example.com', 'pw', department=cls.other_dept,
        )

    def make_item(self, **kwargs):
        defaults = {'title': 'Access review export', 'owner_dept': self.dept}
        defaults.update(kwargs)
        return EvidenceItem.objects.create(**defaults)

    def upload(self, item, content, name='access-review.pdf'):
        item.attachment.save(name, ContentFile(content), save=True)
        item.refresh_from_db()
        return item

    def version_url(self, item, version):
        return reverse('audits:evidence_version_download', kwargs={
            'pk': item.pk, 'version': version,
        })


class EvidenceVersionModelTests(EvidenceVersionBase):
    def test_first_upload_records_version_one_with_its_checksum(self):
        item = self.make_item()
        item.updated_by = self.user
        self.upload(item, PDF)

        version = item.versions.get()
        self.assertEqual(version.version, 1)
        self.assertEqual(version.sha256, hashlib.sha256(PDF).hexdigest())
        self.assertEqual(version.size_bytes, len(PDF))
        self.assertTrue(version.file_name.endswith('.pdf'))
        self.assertEqual(version.uploaded_by, self.user)

    def test_replacing_the_file_keeps_the_earlier_version(self):
        item = self.make_item()
        self.upload(item, PDF)
        first_path = item.versions.get().file_path
        self.upload(item, PDF2)

        versions = list(item.versions.all())
        self.assertEqual([v.version for v in versions], [2, 1])
        self.assertEqual(versions[0].sha256, hashlib.sha256(PDF2).hexdigest())
        self.assertEqual(versions[1].sha256, hashlib.sha256(PDF).hexdigest())
        self.assertEqual(versions[1].file_path, first_path)
        self.assertNotEqual(versions[0].file_path, versions[1].file_path)

    def test_saving_without_a_new_file_adds_no_version(self):
        item = self.make_item()
        self.upload(item, PDF)

        item.notes = 'Reviewed by the auditor.'
        item.save()

        self.assertEqual(item.versions.count(), 1)

    def test_a_file_that_predates_tracking_is_recorded_on_the_next_save(self):
        item = self.make_item()
        legacy_path = 'audit_evidence/legacy.pdf'
        default_storage.save(legacy_path, ContentFile(PDF))
        EvidenceItem.objects.filter(pk=item.pk).update(attachment=legacy_path)

        item.refresh_from_db()
        item.save()

        version = item.versions.get()
        self.assertEqual(version.file_path, legacy_path)
        self.assertEqual(version.sha256, hashlib.sha256(PDF).hexdigest())


class EvidenceVersionDownloadTests(EvidenceVersionBase):
    def setUp(self):
        self.item = self.make_item()
        self.upload(self.item, PDF)
        self.upload(self.item, PDF2)

    def test_the_owner_downloads_a_specific_version(self):
        self.client.force_login(self.user)
        response = self.client.get(self.version_url(self.item, 1))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), PDF)
        self.assertEqual(
            response['X-Checksum-SHA256'],
            hashlib.sha256(PDF).hexdigest(),
        )

    def test_the_latest_version_carries_its_own_checksum(self):
        self.client.force_login(self.user)
        response = self.client.get(self.version_url(self.item, 2))

        self.assertEqual(b''.join(response.streaming_content), PDF2)
        self.assertEqual(
            response['X-Checksum-SHA256'],
            hashlib.sha256(PDF2).hexdigest(),
        )

    def test_another_department_gets_404(self):
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(self.version_url(self.item, 1)).status_code, 404
        )

    def test_signing_in_is_required(self):
        response = self.client.get(self.version_url(self.item, 1))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_unknown_version_is_404(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(self.version_url(self.item, 99)).status_code, 404
        )

    def test_detail_page_lists_versions_and_their_checksums(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('audits:evidence_detail', kwargs={'pk': self.item.pk})
        )

        self.assertContains(response, 'File versions')
        self.assertContains(response, hashlib.sha256(PDF).hexdigest())
        self.assertContains(response, hashlib.sha256(PDF2).hexdigest())


class EvidenceUploadThroughTheFormTests(EvidenceVersionBase):
    def test_upload_stamps_the_creator_and_the_version_uploader(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('audits:evidence_create'), {
            'title': 'Firewall configuration export',
            'evidence_type': 'configuration',
            'owner_dept': self.dept.pk,
            'attachment': SimpleUploadedFile(
                'firewall.pdf', PDF, content_type='application/pdf'
            ),
        })

        self.assertEqual(response.status_code, 302)
        item = EvidenceItem.objects.get(title='Firewall configuration export')
        self.assertEqual(item.created_by, self.user)
        self.assertEqual(item.updated_by, self.user)
        version = item.versions.get()
        self.assertEqual(version.version, 1)
        self.assertEqual(version.uploaded_by, self.user)
        self.assertEqual(version.sha256, hashlib.sha256(PDF).hexdigest())

    def test_replacing_the_attachment_through_the_form_adds_a_version(self):
        item = self.make_item(title='Quarterly access review')
        self.upload(item, PDF)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('audits:evidence_update', kwargs={'pk': item.pk}),
            {
                'title': item.title,
                'evidence_type': item.evidence_type,
                'owner_dept': self.dept.pk,
                'attachment': SimpleUploadedFile(
                    'review-v2.pdf', PDF2, content_type='application/pdf'
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.versions.count(), 2)
        self.assertEqual(
            item.versions.first().sha256,
            hashlib.sha256(PDF2).hexdigest(),
        )
