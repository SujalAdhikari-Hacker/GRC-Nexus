import logging
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from assets.models import Asset
from audits.models import ActionItem
from controls.models import Control
from core.correlation import get_framework_coverage
from core.dashboard_data import compute_trends
from core.mixins import HODOrSuperuserMixin, SuperuserOnlyMixin, scope_queryset
from frameworks.models import Framework
from policies.models import Policy
from risks.models import Risk
from vendors.models import Vendor
from vulnerabilities.models import Finding

from .forms import CustomUserChangeForm, CustomUserCreationForm, DepartmentForm
from .input_validation import choice, positive_int, search_query
from .models import Department, User

logger = logging.getLogger(__name__)


def _severity_band(score):
    """Delegates to the single source of truth in risks.services."""
    from risks.services import severity_band
    return severity_band(score)


# ============================================================
# DASHBOARD
# ============================================================

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # Refresh ticket alerts. Best-effort: a failure here must never take
        # the dashboard down, but it must be logged rather than swallowed.
        # Throttled — a full scan on every dashboard load would re-walk the
        # risk/control/finding set for every page view.
        try:
            from tickets.alerts import scan_and_create_tickets_throttled
            scan_and_create_tickets_throttled()
        except Exception:
            logger.exception('Ticket alert scan failed during dashboard render')

        assets = scope_queryset(Asset.objects.filter(is_active=True), user)
        risks = scope_queryset(Risk.objects.select_related('category'), user)
        active_risks = risks.exclude(status='closed')
        # Materialise once: the value is iterated several times below, and each
        # pass over a lazy queryset would otherwise be another full query.
        active_list = list(active_risks)
        controls = scope_queryset(Control.objects.all(), user)
        policies = scope_queryset(Policy.objects.all(), user)
        vendors = scope_queryset(Vendor.objects.filter(status='active'), user)
        findings = scope_queryset(Finding.objects.all(), user)
        actions = scope_queryset(ActionItem.objects.all(), user)

        # Heatmap (active risks only — closed risks are not live exposure).
        # One GROUP BY instead of 25 COUNT queries.
        heatmap_cells = {
            (row['likelihood'], row['impact']): row['n']
            for row in active_risks.values('likelihood', 'impact').annotate(n=Count('id'))
        }
        heatmap = []
        for impact in range(5, 0, -1):
            row = []
            for likelihood in range(1, 6):
                score = likelihood * impact
                row.append({
                    'likelihood': likelihood,
                    'impact': impact,
                    'count': heatmap_cells.get((likelihood, impact), 0),
                    'band': _severity_band(score),
                    'score': score,
                })
            heatmap.append(row)

        # Category distribution (active risks)
        category_counts = Counter(
            r.category.name if r.category_id else 'Uncategorised' for r in active_list
        )
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

        # Trends (6 calendar months). This also supplies the "risks added"
        # chart — the two were previously computed with separate loops, which
        # doubled the query cost for identical numbers.
        today = timezone.localdate()
        trends = compute_trends(risks, findings, actions, months=6)
        month_labels = trends['trend_labels']
        month_values = trends['risks_created_trend']

        # Framework coverage
        framework_rows = [(fw, get_framework_coverage(fw)) for fw in Framework.objects.all()]

        # Severity summary (active risks) — bands come from risks.services.
        severity_summary = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for r in active_list:
            severity_summary[_severity_band(r.inherent_score)] += 1

        # Top risky assets (active risks only)
        asset_rows = []
        for asset in assets.select_related('owner_dept', 'vendor').prefetch_related('risks'):
            asset_risks = [r for r in asset.risks.all() if r.status != 'closed']
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

        ctx.update({
            'asset_count': assets.count(),
            'risk_count': risks.count(),
            'open_risk_count': active_risks.count(),
            'breached_count': active_risks.filter(appetite_breached=True).count(),
            'control_count': controls.count(),
            'implemented_control_count': controls.filter(status='implemented').count(),
            'policy_count': policies.count(),
            'vendor_count': vendors.count(),
            'top_risks': active_risks.order_by('-residual_score')[:5],
            'recent_assets': assets.order_by('-created_at')[:5],
            'top_risky_assets': asset_rows[:8],
            'framework_rows': framework_rows,
            'is_super': user.is_superuser,
            'heatmap': heatmap,
            'severity_summary': severity_summary,
            # Passed to json_script in the template (safe inline JSON)
            'category_labels': category_labels,
            'category_values': category_values,
            'control_status_data': control_status_data,
            'month_labels': month_labels,
            'month_values': month_values,
        })

        # ---------- Ticket widget stats ----------
        try:
            from tickets.models import Ticket
            ticket_qs = scope_queryset(Ticket.objects.all(), user)
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
            logger.exception('Ticket widget failed to render')
            ctx.update({
                'ticket_open_count': 0,
                'ticket_critical_count': 0,
                'ticket_high_count': 0,
                'ticket_unassigned_count': 0,
                'ticket_my_count': 0,
                'ticket_overdue_count': 0,
                'recent_tickets': [],
            })

        # ---------- Incident widget stats ----------
        try:
            from incidents.models import Incident
            incident_qs = scope_queryset(Incident.objects.all(), user)
            open_incidents = incident_qs.exclude(status='closed')

            ctx['incident_open_count'] = open_incidents.count()
            ctx['incident_critical_count'] = open_incidents.filter(
                severity__in=['critical', 'high']).count()
            ctx['incident_breach_count'] = open_incidents.filter(
                incident_type='data_breach').count()
            ctx['incident_sla_count'] = sum(
                1 for i in open_incidents if i.sla_breached)
            ctx['recent_incidents'] = open_incidents.select_related(
                'owner_dept', 'handler'
            ).order_by('detected_at')[:5]
        except Exception:
            logger.exception('Incident widget failed to render')
            ctx.update({
                'incident_open_count': 0,
                'incident_critical_count': 0,
                'incident_breach_count': 0,
                'incident_sla_count': 0,
                'recent_incidents': [],
            })

        # Trend charts
        ctx.update(trends)
        return ctx


# ============================================================
# GLOBAL SEARCH (command palette)
# ============================================================

@login_required
def global_search(request):
    q = search_query(request.GET.get('q', ''))
    user = request.user

    results = {
        'assets': [], 'risks': [], 'controls': [], 'policies': [], 'vendors': [],
        'findings': [], 'audits': [], 'frameworks': [], 'kris': [],
        'tickets': [], 'actors': [],
    }

    if q:
        from audits.models import Audit
        from kris.models import KRI
        from tickets.models import Ticket
        from threatintel.models import ThreatActor

        results['assets'] = list(
            scope_queryset(Asset.objects.all(), user).filter(
                Q(name__icontains=q) | Q(description__icontains=q) | Q(asset_id__icontains=q)
            )[:5]
        )
        results['risks'] = list(
            scope_queryset(Risk.objects.all(), user).filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )[:5]
        )
        results['controls'] = list(
            scope_queryset(Control.objects.all(), user).filter(
                Q(code__icontains=q) | Q(name__icontains=q)
            )[:5]
        )
        results['policies'] = list(
            scope_queryset(Policy.objects.all(), user).filter(
                Q(code__icontains=q) | Q(title__icontains=q)
            )[:5]
        )
        results['vendors'] = list(
            scope_queryset(Vendor.objects.all(), user).filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )[:5]
        )
        results['findings'] = list(
            scope_queryset(
                Finding.objects.select_related('vulnerability', 'asset'), user
            ).filter(
                Q(vulnerability__cve_id__icontains=q)
                | Q(vulnerability__title__icontains=q)
                | Q(asset__name__icontains=q)
            )[:5]
        )
        results['audits'] = list(
            scope_queryset(Audit.objects.all(), user).filter(
                Q(name__icontains=q)
            )[:5]
        )
        results['frameworks'] = list(
            Framework.objects.filter(name__icontains=q)[:5]
        )
        results['kris'] = list(
            scope_queryset(KRI.objects.all(), user).filter(
                Q(name__icontains=q)
            )[:5]
        )
        results['tickets'] = list(
            scope_queryset(Ticket.objects.all(), user).filter(
                Q(title__icontains=q) | Q(ticket_id__icontains=q)
            )[:5]
        )
        results['actors'] = list(
            ThreatActor.objects.filter(name__icontains=q)[:5]
        )

    total = sum(len(v) for v in results.values())
    return render(request, 'core/_search_results.html', {
        'q': q,
        'results': results,
        'total': total,
    })


# ============================================================
# ADMIN UI — users / departments / roles
# ============================================================

class UserListView(HODOrSuperuserMixin, ListView):
    model = User
    template_name = 'core/users_list.html'
    context_object_name = 'users'
    paginate_by = 30

    def get_queryset(self):
        qs = scope_queryset(
            User.objects.all(), self.request.user, field='department'
        ).select_related('department').prefetch_related('groups')
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q)
            )
        dept = self.request.GET.get('department')
        if dept:
            qs = qs.filter(department_id=positive_int(dept, 'department'))
        role = choice(
            self.request.GET.get('role'), {'hod', 'super', 'user'},
            'role', allow_blank=True,
        )
        if role == 'hod':
            qs = qs.filter(is_hod=True)
        elif role == 'super':
            qs = qs.filter(is_superuser=True)
        elif role == 'user':
            qs = qs.filter(is_hod=False, is_superuser=False)
        return qs.order_by('username')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = scope_queryset(User.objects.all(), self.request.user, field='department')
        ctx['departments'] = Department.objects.all()
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_department'] = self.request.GET.get('department', '')
        ctx['selected_role'] = self.request.GET.get('role', '')
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


class HelpView(LoginRequiredMixin, TemplateView):
    """In-product help: module map, roles, shortcuts and escalation paths."""
    template_name = 'core/help.html'


class RolesPermissionsView(HODOrSuperuserMixin, TemplateView):
    template_name = 'core/roles_permissions.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        groups = Group.objects.all().prefetch_related('permissions')
        rows = []
        for g in groups:
            perms = list(g.permissions.all())
            by_app = {}
            for p in perms:
                app = p.content_type.app_label
                by_app.setdefault(app, []).append(p)
            rows.append({
                'group': g,
                'user_count': g.user_set.count(),
                'perm_count': len(perms),
                'by_app': by_app,
            })
        ctx['rows'] = rows
        ctx['total_groups'] = groups.count()
        return ctx


# ============================================================
# EXECUTIVE PDF REPORT
# ============================================================

from core.executive_report import build_executive_report as _build_exec7  # noqa: E402
from core.reports import render_pdf as _render_pdf7  # noqa: E402


class ExecutiveReportView(LoginRequiredMixin, TemplateView):
    """Full narrative PDF report."""
    template_name = 'reports/executive_report.html'

    def get(self, request, *args, **kwargs):
        ctx = _build_exec7(request.user)
        filename = f'grcnexus_executive_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'
        return _render_pdf7(request, self.template_name, ctx, filename)


def csrf_failure(request, reason=''):
    """Friendly CSRF failure page (never expose the raw reason to the user)."""
    return render(request, '403.html', {
        'message': (
            'Your security token was missing or expired. Reload the page and '
            'try again; if the problem persists, sign out and back in.'
        ),
        'request_path': request.path,
    }, status=403)
