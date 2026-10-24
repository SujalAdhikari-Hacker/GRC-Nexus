"""Regression tests for the shared shell: navigation, metadata and error pages."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username='shell_user', password='demo1234',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_help_page_renders(self):
        response = self.client.get(reverse('core:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Module guide')
        self.assertContains(response, 'Keyboard shortcuts')

    def test_footer_has_links_and_dynamic_year(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'app-footer')
        self.assertContains(response, reverse('core:help'))
        self.assertContains(response, reverse('core:settings'))
        self.assertContains(response, 'GRC Nexus')
        # The copyright year is rendered, not hard-coded.
        self.assertContains(response, '&copy;')

    def test_pages_have_titles_and_meta_descriptions(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, '<title>Dashboard · GRC Nexus</title>', html=False)
        self.assertContains(response, '<meta name="description"', html=False)

    def test_shell_has_mobile_navigation_controls(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'id="mobileNavToggle"')
        self.assertContains(response, 'id="sidebarBackdrop"')
        self.assertContains(response, 'id="sidebarClose"')
        self.assertContains(response, 'aria-controls="sidebar"')

    def test_favicon_variants_are_linked(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'favicon.svg')
        self.assertContains(response, 'favicon.ico')
        self.assertContains(response, 'apple-touch-icon.png')

    def test_custom_404_page(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page not found', status_code=404)
        self.assertContains(response, reverse('core:dashboard'), status_code=404)

    def test_brand_links_to_dashboard(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, f'class="brand" aria-label="GRC Nexus', html=False)
        self.assertContains(response, f'href="{reverse("core:dashboard")}"', html=False)
