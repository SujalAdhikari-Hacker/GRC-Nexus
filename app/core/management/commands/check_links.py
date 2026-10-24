"""Crawl the authenticated UI and report broken links, dead anchors and forms.

Usage:
    python manage.py check_links                 # crawl as "admin"
    python manage.py check_links --user it_hod   # crawl with another role
    python manage.py check_links --max 500       # raise the page budget

The crawler follows same-site links from the dashboard, so it covers every
module reachable from the sidebar and in-page links. It never submits forms:
it only reports form actions that are empty or point at "#".
"""
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.form_actions = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href') is not None:
            self.links.append(attrs['href'])
        elif tag == 'form':
            self.form_actions.append(attrs.get('action') or '')


class Command(BaseCommand):
    help = 'Crawl the UI as a real user and report broken links and dead form actions.'

    def add_arguments(self, parser):
        parser.add_argument('--user', default='admin', help='Username to crawl as (default: admin).')
        parser.add_argument('--max', type=int, default=300, help='Maximum pages to fetch (default: 300).')
        parser.add_argument(
            '--include-admin', action='store_true',
            help='Also crawl Django admin (skipped by default).',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options['user'])
        except User.DoesNotExist:
            raise CommandError(f'User "{options["user"]}" does not exist.')

        client = Client(SERVER_NAME='localhost')
        client.force_login(user)

        queue = deque([('/', None)])
        seen = set()
        broken = []
        dead = []
        checked = 0

        while queue and checked < options['max']:
            path, referrer = queue.popleft()
            if path in seen:
                continue
            seen.add(path)
            checked += 1

            try:
                response = client.get(path)
            except Exception as exc:  # noqa: BLE001 - report, don't abort the crawl
                broken.append((path, 'exception', repr(exc), referrer))
                continue

            if response.status_code >= 400:
                broken.append((path, response.status_code, response.get('Location', ''), referrer))
                continue

            content_type = response.get('Content-Type', '')
            if 'text/html' not in content_type:
                continue

            try:
                body = response.content.decode(response.charset or 'utf-8', errors='replace')
            except Exception:  # noqa: BLE001
                continue

            parser = _LinkParser()
            parser.feed(body)

            for href in parser.links:
                href = (href or '').strip()
                if href == '#main-content':
                    continue  # the accessibility skip link
                if not href or href == '#' or href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
                    dead.append((path, href or '(empty)'))
                    continue
                if href.startswith(('http://', 'https://')):
                    parsed = urlparse(href)
                    if parsed.netloc not in ('localhost', 'localhost:8000'):
                        continue
                    href = parsed.path or '/'
                    if parsed.query:
                        href += '?' + parsed.query
                if not href.startswith('/'):
                    continue
                if href.startswith(('/logout', '/static/', '/media/', '/jsi18n/')):
                    continue
                if href.startswith('/admin/') and not options['include_admin']:
                    continue
                queue.append((href, path))

            for action in parser.form_actions:
                # An empty action posts back to the current URL, which is valid.
                if action == '#':
                    dead.append((path, 'form action #'))

        self.stdout.write('')
        self.stdout.write(f'Crawled {checked} page(s) as "{user.username}".')
        if dead:
            self.stdout.write(self.style.WARNING(f'Dead anchors / form actions: {len(dead)}'))
            for page, href in dead[:40]:
                self.stdout.write(f'  {page} -> {href}')
        if broken:
            self.stdout.write(self.style.ERROR(f'Broken links: {len(broken)}'))
            for path, status, detail, referrer in broken:
                self.stdout.write(f'  [{status}] {path} (from {referrer or "seed"}) {detail}'.rstrip())
            raise CommandError(f'{len(broken)} broken link(s) found.')
        self.stdout.write(self.style.SUCCESS('No broken links found.'))
