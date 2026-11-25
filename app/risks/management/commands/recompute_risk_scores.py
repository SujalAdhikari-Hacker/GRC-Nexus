"""Recompute residual scores and appetite breaches for every risk.

Run this once after deploying a change to the residual-scoring model so that
stored scores match the current formula:

    python manage.py recompute_risk_scores
"""
from core.management.base import LoggedCommand

from risks.services import recompute_all_risks


class Command(LoggedCommand):
    help = 'Recompute residual_score, appetite_breached and escalated for all risks.'

    def handle(self, *args, **options):
        count = recompute_all_risks()
        self.record_counts(risks=count)
        self.stdout.write(self.style.SUCCESS(f'Recomputed {count} risk(s).'))
