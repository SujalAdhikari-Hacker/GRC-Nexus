from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from assets.models import Asset
from risks.models import Risk
from controls.models import Control
from policies.models import Policy
from vendors.models import Vendor
from frameworks.models import Framework
from core.correlation import get_framework_coverage


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

        # Framework coverage — always org-wide (frameworks are shared)
        framework_rows = []
        for fw in Framework.objects.all():
            framework_rows.append((fw, get_framework_coverage(fw)))

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
        })
        return ctx