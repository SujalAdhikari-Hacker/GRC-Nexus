"""Tests for asset dependency graph."""
from core.models import Department, User

from django.test import TestCase

from .models import Asset


class DependencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Dep Dept')
        cls.user = User.objects.create_user('assetdep', 'ad@example.com', 'pw', department=cls.dept)
        cls.db = Asset.objects.create(name='Core database', owner_dept=cls.dept, criticality=4)
        cls.app = Asset.objects.create(name='Web application', owner_dept=cls.dept, criticality=3)

    def test_app_depends_on_db(self):
        self.app.depends_on.add(self.db)
        self.assertIn(self.db, self.app.depends_on.all())
        self.assertIn(self.app, self.db.dependents.all())

    def test_cycles_are_allowed_but_harmless(self):
        self.app.depends_on.add(self.db)
        self.db.depends_on.add(self.app)  # a misconfiguration, not an error
        self.assertEqual(self.app.depends_on.count(), 1)
        self.assertEqual(self.db.depends_on.count(), 1)

    def test_dependents_are_visible_on_detail_for_own_dept(self):
        self.app.depends_on.add(self.db)
        self.client.force_login(self.user)
        resp = self.client.get(f'/assets/{self.db.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Web application')

    def test_edit_form_includes_dependency_field(self):
        self.client.force_login(self.user)
        resp = self.client.get(f'/assets/{self.app.pk}/edit/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="depends_on"')

    def test_other_department_asset_not_editable(self):
        other = Department.objects.create(name='Stranger Dept')
        other_user = User.objects.create_user('sdep', 'sd@example.com', 'pw', department=other)
        self.client.force_login(other_user)
        resp = self.client.get(f'/assets/{self.app.pk}/edit/')
        self.assertEqual(resp.status_code, 404)
