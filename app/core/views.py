from collections import Counter
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from assets.models import Asset
from risks.models import Risk
from controls.models import Control
from policies.models import Policy
from vendors.models import Vendor
from frameworks.models import Framework
from core.correlation import get_framework_coverage


# Severity bands for heatmap cells
def _severity_band(score):
    if score >= 20:
        return 'critical'
    if score >= 12:
        return 'high'
    if score >= 6:
        return 'medium'
    return 'low'


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        is_super = user.is_superuser

        assets = Asset.objects.filter(is_active=True)
        risks = Risk.objects.all()
        controls = Control.objects.all()
        policies = Policy.objects.all()
        vendors = Vendor.objects.filter(is_active=True)

        if not is_super:
            assets = assets.filter(owner_dept=user.department)
            risks = risks.filter(owner_dept=user.department)
            controls = controls.filter(owner_dept=user.department)
            policies = policies.filter(owner_dept=user.department)
            vendors = vendors.filter(owner_dept=user.department)

        # ----------------------------------------------------------------
        # HEATMAP: 5x5 matrix [impact][likelihood]
        # impact 5 (top row) → 1 (bottom row)
        # likelihood 1 (left col) → 5 (right col)
        # Each cell: { count, band }
        # ----------------------------------------------------------------
        heatmap = []
        for impact in range(5, 0, -1):
            row = []
            for likelihood in range(1, 6):
                count = risks.filter(likelihood=likelihood, impact=impact).count()
                score = likelihood * impact
                row.append({
                    'likelihood': likelihood,
                    'impact': impact,
                    'count': count,
                    'band': _severity_band(score),
                    'score': score,
                })
            heatmap.append(row)

        # ----------------------------------------------------------------
        # DISTRIBUTION: risks per category
        # ----------------------------------------------------------------
        category_counts = Counter(r.category.name for r in risks)
        category_labels = list(category_counts.keys())
        category_values = list(category_counts.values())

        # ----------------------------------------------------------------
        # CONTROL STATUS: bar chart
        # ----------------------------------------------------------------
        control_status_counts = Counter(controls.values_list('status', flat=True))
        control_status_data = {
            'planned':         control_status_counts.get('planned', 0),
            'implemented':     control_status_counts.get('implemented', 0),
            'not_implemented': control_status_counts.get('not_implemented', 0),
            'not_applicable':  control_status_counts.get('not_applicable', 0),
        }

        # ----------------------------------------------------------------
        # TREND: risks added per month for last 6 months
        # ----------------------------------------------------------------
        today = timezone.now().date()
        month_labels = []
        month_values = []
        for i in range(5, -1, -1):
            # first day of month i months ago
            target = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            next_month = (target + timedelta(days=32)).replace(day=1)
            count = risks.filter(
                created_at__date__gte=target,
                created_at__date__lt=next_month,
            ).count()
            month_labels.append(target.strftime('%b %Y'))
            month_values.append(count)

        # ----------------------------------------------------------------
        # FRAMEWORK COVERAGE (existing)
        # ----------------------------------------------------------------
        framework_rows = []
        for fw in Framework.objects.all():
            framework_rows.append((fw, get_framework_coverage(fw)))

        # ----------------------------------------------------------------
        # SEVERITY SUMMARY (for the heatmap legend and stats)
        # ----------------------------------------------------------------
        severity_summary = {
            'critical': sum(1 for r in risks if r.inherent_score >= 20),
            'high':     sum(1 for r in risks if 12 <= r.inherent_score < 20),
            'medium':   sum(1 for r in risks if 6 <= r.inherent_score < 12),
            'low':      sum(1 for r in risks if r.inherent_score < 6),
        }

        ctx.update({
            'asset_count': assets.count(),
            'risk_count': risks.count(),
            'open_risk_count': risks.exclude(status='closed').count(),
            'breached_count': risks.filter(appetite_breached=True).count(),
            'control_count': controls.count(),
            'implemented_control_count': controls.filter(status='implemented').count(),
            'policy_count': policies.count(),
            'vendor_count': vendors.count(),
            'top_risks': risks.order_by('-residual_score')[:5],
            'recent_assets': assets.order_by('-created_at')[:5],
            'framework_rows': framework_rows,
            'is_super': is_super,

            # Chart data
            'heatmap': heatmap,
            'severity_summary': severity_summary,
            'category_labels': category_labels,
            'category_values': category_values,
            'control_status_data': control_status_data,
            'month_labels': month_labels,
            'month_values': month_values,
        })
        return ctx