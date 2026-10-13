import json
from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from core.mixins import HODOrSuperuserMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, CreateView, UpdateView

from assets.models import Asset
from risks.models import Risk
from controls.models import Control
from policies.models import Policy
from vendors.models import Vendor
from frameworks.models import Framework
from vulnerabilities.models import Finding
from audits.models import ActionItem
from core.correlation import get_framework_coverage
from core.dashboard_data import compute_trends
from .models import User, Department
from .forms import CustomUserCreationForm, CustomUserChangeForm, DepartmentForm


def _severity_band(score):
    if score >= 20:
        return 'critical'
    if score >= 12:
        return 'high'
    if score >= 6:
        return 'medium'
    return 'low'


# ============================================================
# DASHBOARD
# ============================================================

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

        # Refresh alerts once per dashboard load
    from tickets.alerts import scan_and_create_tickets
    try:
            scan_and_create_tickets(verbose=False)
    except Exception:
            pass
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        is_super = user.is_superuser

        assets = Asset.objects.filter(is_active=True)
        risks = Risk.objects.all()
        controls = Control.objects.all()
        policies = Policy.objects.all()
        vendors = Vendor.objects.filter(status='active')
        findings = Finding.objects.all()
        actions = ActionItem.objects.all()

        if not is_super:
            assets = assets.filter(owner_dept=user.department)
            risks = risks.filter(owner_dept=user.department)
            controls = controls.filter(owner_dept=user.department)
            policies = policies.filter(owner_dept=user.department)
            vendors = vendors.filter(owner_dept=user.department)
            findings = findings.filter(owner_dept=user.department)
            actions = actions.filter(owner_dept=user.department)

        # Heatmap
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

        # Category distribution
        category_counts = Counter(r.category.name for r in risks)
        category_labels = list(category_counts.keys())
        category_values = list(category_counts.values())

        # Control status
        control_status_counts = Counter(controls.values_list('status', flat=True))
        control_status_data = {
            'planned':         control_status_counts.get('planned', 0),
            'implemented':     control_status_counts.get('implemented', 0),
            'not_implemented': control_status_counts.get('not_implemented', 0),
            'not_applicable':  control_status_counts.get('not_applicable', 0),
        }

        # Risks added per month
        today = timezone.now().date()
        month_labels = []
        month_values = []
        for i in range(5, -1, -1):
            target = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            next_month = (target + timedelta(days=32)).replace(day=1)
            count = risks.filter(
                created_at__date__gte=target,
                created_at__date__lt=next_month,
            ).count()
            month_labels.append(target.strftime('%b %Y'))
            month_values.append(count)

        # Framework coverage
        framework_rows = []
        for fw in Framework.objects.all():
            framework_rows.append((fw, get_framework_coverage(fw)))

        # Severity summary
        severity_summary = {
            'critical': sum(1 for r in risks if r.inherent_score >= 20),
            'high':     sum(1 for r in risks if 12 <= r.inherent_score < 20),
            'medium':   sum(1 for r in risks if 6 <= r.inherent_score < 12),
            'low':      sum(1 for r in risks if r.inherent_score < 6),
        }
        # Top risky assets
        asset_rows = []
        for asset in assets.select_related('owner_dept', 'vendor'):
            asset_risks = list(asset.risks.all())
            if not asset_risks:
                continue
            max_residual = max((r.residual_score or 0) for r in asset_risks)
            sum_residual = sum((r.residual_score or 0) for r in asset_risks)
            breached = any(r.appetite_breached for r in asset_risks)
            exposure = max_residual * (asset.criticality or 1)
            asset_rows.append({
                'asset': asset,
                'risk_count': len(asset_risks),
                'max_residual': max_residual,
                'sum_residual': sum_residual,
                'breached': breached,
                'exposure': exposure,
                'top_risk': max(asset_risks, key=lambda r: r.residual_score or 0),
            })
        asset_rows.sort(key=lambda x: -x['exposure'])
        top_risky_assets = asset_rows[:8]

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
            'top_risky_assets': top_risky_assets,
            'framework_rows': framework_rows,
            'is_super': is_super,
            'heatmap': heatmap,
            'severity_summary': severity_summary,
            # Serialized for inline JS — prevents breakage on special characters
            'category_labels_json': json.dumps(category_labels),
            'category_values_json': json.dumps(category_values),
            'control_status_data_json': json.dumps(control_status_data),
            'month_labels_json': json.dumps(month_labels),
            'month_values_json': json.dumps(month_values),
        })

        # ---------- Ticket widget stats ----------
        try:
            from tickets.models import Ticket
            ticket_qs = Ticket.objects.all()
            if not is_super and user.department_id:
                ticket_qs = ticket_qs.filter(owner_dept=user.department)

            open_statuses = ['open', 'assigned', 'in_progress', 'blocked']
            open_tickets = ticket_qs.filter(status__in=open_statuses)

            ctx['ticket_open_count'] = open_tickets.count()
            ctx['ticket_critical_count'] = open_tickets.filter(priority=4).count()
            ctx['ticket_high_count'] = open_tickets.filter(priority=3).count()
            ctx['ticket_unassigned_count'] = open_tickets.filter(assigned_to__isnull=True).count()
            ctx['ticket_my_count'] = open_tickets.filter(assigned_to=user).count()
            ctx['ticket_overdue_count'] = sum(1 for t in open_tickets if t.is_overdue)
            ctx['recent_tickets'] = open_tickets.select_related(
                'owner_dept', 'assigned_to'
            ).order_by('-priority', 'due_date', '-created_at')[:5]
        except Exception:
            ctx['ticket_open_count'] = 0
            ctx['ticket_critical_count'] = 0
            ctx['ticket_high_count'] = 0
            ctx['ticket_unassigned_count'] = 0
            ctx['ticket_my_count'] = 0
            ctx['ticket_overdue_count'] = 0
            ctx['recent_tickets'] = []

        # Trend charts
        ctx.update(compute_trends(risks, findings, actions, months=6))
        return ctx


# ============================================================
# GLOBAL SEARCH (command palette)
# ============================================================

@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    user = request.user
    is_super = user.is_superuser

    def scoped(qs):
        if is_super:
            return qs
        if not user.department_id:
            return qs.none()
        return qs.filter(owner_dept=user.department)

    results = {'assets': [], 'risks': [], 'controls': [], 'policies': [], 'vendors': []}

    if q:
        results['assets'] = list(
            scoped(Asset.objects.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(asset_id__icontains=q)))[:5]
        )
        results['risks'] = list(
            scoped(Risk.objects.filter(Q(title__icontains=q) | Q(description__icontains=q)))[:5]
        )
        results['controls'] = list(
            scoped(Control.objects.filter(Q(code__icontains=q) | Q(name__icontains=q)))[:5]
        )
        results['policies'] = list(
            scoped(Policy.objects.filter(Q(code__icontains=q) | Q(title__icontains=q)))[:5]
        )
        results['vendors'] = list(
            scoped(Vendor.objects.filter(Q(name__icontains=q) | Q(description__icontains=q)))[:5]
        )

    total = sum(len(v) for v in results.values())
    return render(request, 'core/_search_results.html', {
        'q': q,
        'results': results,
        'total': total,
    })




class SuperuserOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser


class UserListView(HODOrSuperuserMixin, ListView):
    model = User
    template_name = 'core/users_list.html'
    context_object_name = 'users'
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.all().select_related('department').prefetch_related('groups')
        user = self.request.user
        if not user.is_superuser and user.department_id:
            qs = qs.filter(department=user.department)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
        dept = self.request.GET.get('department')
        if dept:
            qs = qs.filter(department_id=dept)
        role = self.request.GET.get('role')
        if role == 'hod':
            qs = qs.filter(is_hod=True)
        elif role == 'super':
            qs = qs.filter(is_superuser=True)
        elif role == 'user':
            qs = qs.filter(is_hod=False, is_superuser=False)
        return qs.order_by('username')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['departments'] = Department.objects.all()
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_department'] = self.request.GET.get('department', '')
        ctx['selected_role'] = self.request.GET.get('role', '')
        user = self.request.user
        base = User.objects.all()
        if not user.is_superuser and user.department_id:
            base = base.filter(department=user.department)
        ctx['total_count'] = base.count()
        ctx['hod_count'] = base.filter(is_hod=True).count()
        ctx['super_count'] = base.filter(is_superuser=True).count()
        return ctx


class UserCreateView(SuperuserOnlyMixin, CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('core:users_list')


class UserUpdateView(SuperuserOnlyMixin, UpdateView):
    model = User
    form_class = CustomUserChangeForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('core:users_list')


class DepartmentListView(HODOrSuperuserMixin, ListView):
    model = Department
    template_name = 'core/departments_list.html'
    context_object_name = 'departments'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for d in self.object_list:
            rows.append({
                'dept': d,
                'user_count': d.users.count(),
                'asset_count': d.assets.count(),
                'risk_count': d.risks.count(),
                'control_count': d.controls.count(),
                'hod': d.users.filter(is_hod=True).first(),
            })
        ctx['rows'] = rows
        return ctx


class DepartmentCreateView(SuperuserOnlyMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'core/department_form.html'
    success_url = reverse_lazy('core:departments_list')


class DepartmentUpdateView(SuperuserOnlyMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'core/department_form.html'
    success_url = reverse_lazy('core:departments_list')


class RolesPermissionsView(HODOrSuperuserMixin, TemplateView):
    template_name = 'core/roles_permissions.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        groups = Group.objects.all().prefetch_related('permissions')
        rows = []
        for g in groups:
            perms = g.permissions.all()
            by_app = {}
            for p in perms:
                app = p.content_type.app_label
                by_app.setdefault(app, []).append(p)
            rows.append({
                'group': g,
                'user_count': g.user_set.count(),
                'perm_count': perms.count(),
                'by_app': by_app,
            })
        ctx['rows'] = rows
        ctx['total_groups'] = groups.count()
        return ctx




# ============================================================
# EXECUTIVE PDF REPORT
# ============================================================

from django.shortcuts import render as _rn7
from django.http import HttpResponse as _HR7
from core.reports import render_pdf as _render_pdf7
from core.executive_report import build_executive_report as _build_exec7


class ExecutiveReportView(LoginRequiredMixin, TemplateView):
    """Full narrative PDF report."""
    template_name = 'reports/executive_report.html'

    def get(self, request, *args, **kwargs):
        ctx = _build_exec7(request.user)
        from django.utils import timezone
        filename = f'grcnexus_executive_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'
        return _render_pdf7(request, self.template_name, ctx, filename)
