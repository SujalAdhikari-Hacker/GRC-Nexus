"""Recompute stored Finding.composite_score values to match the 55/30/15 formula."""
from decimal import Decimal

from django.db import migrations


def recompute_finding_composite_scores(apps, schema_editor):
    Finding = apps.get_model('vulnerabilities', 'Finding')
    crit_map = {1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}

    for finding in Finding.objects.select_related('vulnerability', 'asset').all():
        if not finding.vulnerability_id or not finding.asset_id:
            score = Decimal('0.00')
        else:
            cvss = float(finding.vulnerability.cvss_score or 0)
            severity = max(0.0, min(1.0, cvss / 10.0))
            asset_factor = crit_map.get(finding.asset.criticality, 0.5)
            threat = float(finding.vulnerability.epss_score or 0)
            if finding.vulnerability.kev_status:
                threat += 0.5
            threat = max(0.0, min(1.0, threat))
            val = round(100.0 * (0.55 * severity + 0.30 * asset_factor + 0.15 * threat), 2)
            score = Decimal(f'{val:.2f}')

        if abs(float(finding.composite_score or 0) - float(score)) > 0.005:
            Finding.objects.filter(pk=finding.pk).update(composite_score=score)


class Migration(migrations.Migration):
    dependencies = [
        ('vulnerabilities', '0006_alter_historicalvulnerability_source_and_more'),
        ('guardian', '__latest__'),
        ('assets', '__latest__'),
    ]

    operations = [
        migrations.RunPython(recompute_finding_composite_scores, migrations.RunPython.noop),
    ]
