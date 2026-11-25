"""Load the Nepal regulatory frameworks from the JSON catalogues in ``frameworks/data``.

The catalogues are plain JSON so the repo stays self-contained: the NRB
requirement sheets were transcribed once from the NRB publications, and the
Nepal acts / NRB directives entries are curated summaries because the official
gazette text is not distributed with this repository.

    python manage.py seed_nrb_frameworks
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from frameworks.models import Framework, FrameworkControl

DATA_DIR = Path(__file__).resolve().parents[2] / 'data'

CATALOGUES = (
    {
        'file': 'nrb_cyber_resilience_2023.json',
        'name': 'NRB Cyber Resilience Guidelines',
        'version': '2023',
        'description': (
            'Nepal Rastra Bank Cyber Resilience Guidelines (August 2023), '
            'sections B to I. 185 requirements transcribed from the NRB '
            'requirement catalogue, each carrying its Mandatory or Should '
            'obligation.'
        ),
    },
    {
        'file': 'nrb_ai_guidelines_2025.json',
        'name': 'NRB Artificial Intelligence Guidelines',
        'version': 'Dec 2025',
        'description': (
            'Nepal Rastra Bank Artificial Intelligence Guidelines (December '
            '2025). 61 requirements covering governance and accountability, '
            'transparency and explainability, fairness, data and model risk, '
            'and third-party AI.'
        ),
    },
    {
        'file': 'nepal_digital_acts.json',
        'name': 'Nepal Digital & Electronic Acts',
        'version': '2063-2075',
        'description': (
            'Curated summary of Nepal\'s digital and electronic laws: '
            'Electronic Transactions Act 2063 (2008), Electronic Transactions '
            'Rules 2064 (2008) and Individual Privacy Act 2075 (2018). '
            'Summaries only - check the published act before relying on them '
            'for legal advice.'
        ),
    },
    {
        'file': 'nrb_it_directives.json',
        'name': 'NRB IT & Cyber Security Directives',
        'version': 'curated',
        'description': (
            'Curated summary of Nepal Rastra Bank IT and cyber security '
            'directives for banks and financial institutions: governance, IT '
            'risk, continuity, incident reporting, customer data, outsourcing, '
            'audit, testing, access, change, logging and awareness. Summaries '
            'only - check the directive in force for your institution class.'
        ),
    },
)


class Command(BaseCommand):
    help = 'Seed the NRB frameworks and the Nepal digital/electronic acts.'

    @transaction.atomic
    def handle(self, *args, **options):
        for catalogue in CATALOGUES:
            path = DATA_DIR / catalogue['file']
            if not path.exists():
                raise CommandError(f'Catalogue not found: {path}')

            try:
                requirements = json.loads(path.read_text(encoding='utf-8'))
            except ValueError as exc:
                raise CommandError(f'{path.name} is not valid JSON: {exc}')

            framework, _ = Framework.objects.update_or_create(
                name=catalogue['name'],
                defaults={
                    'version': catalogue['version'],
                    'description': catalogue['description'],
                },
            )

            created = updated = 0
            for item in requirements:
                _control, was_created = FrameworkControl.objects.update_or_create(
                    framework=framework,
                    code=item['code'],
                    defaults={
                        'title': item['title'],
                        'description': item.get('description', ''),
                    },
                )
                created += was_created
                updated += not was_created

            self.stdout.write(self.style.SUCCESS(
                f'{framework}: {len(requirements)} requirement(s) '
                f'({created} created, {updated} updated)'
            ))
