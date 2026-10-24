"""Statement of Applicability (SoA).

The SoA is the mandatory ISO 27001 annex document: for every control in the
framework, state whether it applies to the organisation, which internal
control satisfies it, and what the residual gaps are. Auditors read it first.

This report is derived, not maintained: one row per ``FrameworkControl``,
combining the internal-control mappings (``ControlFrameworkMapping``), those
controls' implementation status, and the newest compliance-assessment item's
verdict. Because it derives from live data it cannot drift the way a
hand-maintained spreadsheet does.
"""
import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import View

from controls.models import ControlFrameworkMapping
from .models import ComplianceAssessment, Framework

_APPLICABLE_RELATIONSHIPS = ('equal', 'superset', 'subset', 'intersects')


def _coverage_state(mapping_rows, assessment_status):
    """Classify one framework requirement into an SoA verdict."""
    weighted = any(
        m.relationship in _APPLICABLE_RELATIONSHIPS for m in mapping_rows
    )
    if assessment_status == 'na':
        return 'excluded', 'bg-secondary'
    if assessment_status == 'non_compliant':
        return 'gap — non-compliant', 'bg-danger'
    if assessment_status == 'partial':
        return 'gap — partially compliant', 'bg-warning'
    if mapping_rows:
        if all(m.control.status == 'implemented' for m in mapping_rows):
            return ('covered', 'bg-success' if weighted else 'bg-secondary')
        if any(m.control.status == 'implemented' for m in mapping_rows):
            return 'partially covered', 'bg-warning'
        return 'mapped, not implemented', 'bg-warning'
    return 'no internal control', 'bg-danger'


class SoAReportView(LoginRequiredMixin, View):
    """`/frameworks/soa/` — HTML report and `?export=csv` for auditors."""

    template_name = 'frameworks/soa_report.html'

    def get(self, request, *args, **kwargs):
        frameworks = Framework.objects.order_by('name')
        framework_id = request.GET.get('framework')
        framework = None
        if framework_id:
            framework = Framework.objects.filter(pk=framework_id).first()
        if framework is None:
            framework = frameworks.first()  # the default, read-only page

        if framework is None:
            context = {
                'frameworks': frameworks,
                'framework': None,
                'rows': [],
                'no_framework': True,
            }
            return render(request, self.template_name, context)

        # Newest assessment for this framework, for the verdict column.
        assessment = (
            ComplianceAssessment.objects
            .filter(framework=framework)
            .order_by('-assessment_date', '-pk')
            .first()
        )
        item_status = {}
        if assessment:
            item_status = {
                item.framework_control_id: item.status
                for item in assessment.items.all()
            }

        # Mappings grouped by requirement — two queries total.
        mappings = (
            ControlFrameworkMapping.objects
            .filter(framework_control__framework=framework)
            .select_related('control', 'framework_control')
        )
        by_requirement = {}
        for mapping in mappings:
            by_requirement.setdefault(
                mapping.framework_control_id, []).append(mapping)

        rows = []
        counts = {}
        for requirement in framework.controls.order_by('code').all():
            mapping_rows = by_requirement.get(requirement.pk, [])
            mapped = sorted(mapping_rows, key=lambda m: m.control.code)
            status = item_status.get(requirement.pk, '') or ''
            verdict, badge = _coverage_state(mapped, status)
            counts[verdict] = counts.get(verdict, 0) + 1
            rows.append({
                'requirement': requirement,
                'mapped': mapped,
                'assessment_status': status,
                'verdict': verdict,
                'verdict_badge': badge,
            })

        if request.GET.get('export') == 'csv':
            return self._export_csv(framework, rows)

        context = {
            'frameworks': frameworks,
            'framework': framework,
            'rows': rows,
            'assessment': assessment,
            'counts': counts,
            'total': len(rows),
            'generated_at': timezone.now(),
        }
        return render(request, self.template_name, context)

    def _export_csv(self, framework, rows):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        slug = framework.name.lower().replace(' ', '-')
        response['Content-Disposition'] = (
            f'attachment; filename="soa-{slug}.csv"'
        )
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow([
            'Control code', 'Requirement title', 'Requirement description',
            'Applicable', 'Verdict',
            'Internal control(s)', 'Relationship',
            'Internal control status',
            'Assessment status',
        ])
        for row in rows:
            requirement = row['requirement']
            writer.writerow([
                requirement.code,
                requirement.title,
                (requirement.description or '')[:400],
                'no' if row['assessment_status'] == 'na' else 'yes',
                row['verdict'],
                ' | '.join(m.control.code for m in row['mapped']) or '-',
                ' | '.join(m.get_relationship_display() for m in row['mapped']) or '-',
                ' | '.join(m.control.get_status_display() for m in row['mapped']) or '-',
                row['assessment_status'].replace('_', ' ') or '-',
            ])
        writer.writerow([])  # spacer
        return response