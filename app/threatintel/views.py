from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, DetailView, TemplateView

from .models import Tactic, Technique, ThreatActor, IOC, IOCFeedSync


# ============================================================
# THREAT INTEL OVERVIEW
# ============================================================

class ThreatIntelOverviewView(LoginRequiredMixin, TemplateView):
    template_name = 'threatintel/overview.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now()
        last_24h = today - timedelta(hours=24)
        last_7d = today - timedelta(days=7)

        # IOC stats
        ctx['ioc_total'] = IOC.objects.filter(is_active=True).count()
        ctx['ioc_24h'] = IOC.objects.filter(created_at__gte=last_24h).count()
        ctx['ioc_7d'] = IOC.objects.filter(created_at__gte=last_7d).count()
        ctx['ioc_whitelisted'] = IOC.objects.filter(is_whitelisted=True).count()

        # ATT&CK stats
        ctx['tactic_count'] = Tactic.objects.count()
        ctx['technique_count'] = Technique.objects.filter(deprecated=False).count()
        ctx['actor_count'] = ThreatActor.objects.count()

        # Breakdowns
        ctx['by_type'] = (
            IOC.objects.filter(is_active=True)
            .values('ioc_type')
            .annotate(c=Count('id'))
            .order_by('-c')[:8]
        )
        ctx['by_threat'] = (
            IOC.objects.filter(is_active=True)
            .values('threat_type')
            .annotate(c=Count('id'))
            .order_by('-c')
        )
        ctx['by_source'] = (
            IOC.objects.filter(is_active=True)
            .values('source')
            .annotate(c=Count('id'))
            .order_by('-c')
        )
        ctx['by_confidence'] = (
            IOC.objects.filter(is_active=True)
            .values('confidence')
            .annotate(c=Count('id'))
            .order_by('-confidence')
        )

        # Top malware families
        ctx['top_malware'] = (
            IOC.objects.filter(is_active=True)
            .exclude(malware_family='')
            .values('malware_family')
            .annotate(c=Count('id'))
            .order_by('-c')[:10]
        )

        # Recent IOCs (preview)
        ctx['recent_iocs'] = IOC.objects.filter(is_active=True).order_by('-created_at')[:10]

        # Recent sync runs
        ctx['recent_syncs'] = IOCFeedSync.objects.all()[:5]

        # MITRE tactic distribution
        tactic_rows = []
        for t in Tactic.objects.all().order_by('order'):
            tactic_rows.append({
                'tactic': t,
                'technique_count': t.techniques.count(),
                'ioc_count': IOC.objects.filter(techniques__tactics=t).distinct().count(),
            })
        ctx['tactic_rows'] = tactic_rows

        return ctx


# ============================================================
# IOC FEED (list)
# ============================================================

class IOCFeedView(LoginRequiredMixin, ListView):
    model = IOC
    template_name = 'threatintel/ioc_feed.html'
    context_object_name = 'iocs'
    paginate_by = 50

    def get_queryset(self):
        qs = IOC.objects.filter(is_active=True).select_related('threat_actor')

        # Filters
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(value__icontains=q) |
                Q(malware_family__icontains=q) |
                Q(notes__icontains=q)
            )

        ioc_type = self.request.GET.get('type')
        if ioc_type:
            qs = qs.filter(ioc_type=ioc_type)

        threat_type = self.request.GET.get('threat')
        if threat_type:
            qs = qs.filter(threat_type=threat_type)

        source = self.request.GET.get('source')
        if source:
            qs = qs.filter(source=source)

        conf = self.request.GET.get('confidence')
        if conf:
            qs = qs.filter(confidence=conf)

        days = self.request.GET.get('days')
        if days:
            try:
                cutoff = timezone.now() - timedelta(days=int(days))
                qs = qs.filter(first_seen__gte=cutoff)
            except (ValueError, TypeError):
                pass

        return qs.order_by('-first_seen', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['ioc_types'] = IOC.IOC_TYPE_CHOICES
        ctx['threat_types'] = IOC.THREAT_TYPE_CHOICES
        ctx['confidences'] = IOC.CONFIDENCE_CHOICES
        ctx['sources'] = (
            IOC.objects.values_list('source', flat=True).distinct().order_by('source')
        )
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_threat'] = self.request.GET.get('threat', '')
        ctx['selected_source'] = self.request.GET.get('source', '')
        ctx['selected_confidence'] = self.request.GET.get('confidence', '')
        ctx['days_filter'] = self.request.GET.get('days', '')

        base = IOC.objects.filter(is_active=True)
        last_24h = timezone.now() - timedelta(hours=24)
        last_7d = timezone.now() - timedelta(days=7)
        ctx['total_count'] = base.count()
        ctx['count_24h'] = base.filter(created_at__gte=last_24h).count()
        ctx['count_7d'] = base.filter(created_at__gte=last_7d).count()
        ctx['count_high_conf'] = base.filter(confidence__gte=3).count()
        return ctx


class IOCDetailView(LoginRequiredMixin, DetailView):
    model = IOC
    template_name = 'threatintel/ioc_detail.html'
    context_object_name = 'ioc'


# ============================================================
# ATT&CK MATRIX
# ============================================================

class AttackMatrixView(LoginRequiredMixin, TemplateView):
    template_name = 'threatintel/attack_matrix.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        tactics = list(Tactic.objects.all().order_by('order'))

        # Get all techniques with their tactic mapping + IOC count
        techniques = (
            Technique.objects.filter(deprecated=False)
            .prefetch_related('tactics')
            .annotate(ioc_count=Count('iocs', distinct=True))
        )

        # Build columns: tactic -> list of techniques
        columns = []
        for t in tactics:
            col_techniques = []
            for tech in techniques:
                if tech.is_subtechnique:
                    continue
                tactic_ids = set(tt.pk for tt in tech.tactics.all())
                if t.pk in tactic_ids:
                    col_techniques.append({
                        'technique': tech,
                        'ioc_count': tech.ioc_count,
                        'has_iocs': tech.ioc_count > 0,
                    })
            col_techniques.sort(key=lambda x: x['technique'].attack_id)
            columns.append({
                'tactic': t,
                'techniques': col_techniques,
                'technique_count': len(col_techniques),
                'total_iocs': sum(x['ioc_count'] for x in col_techniques),
            })

        ctx['columns'] = columns
        ctx['total_tactics'] = len(tactics)
        ctx['total_techniques'] = sum(c['technique_count'] for c in columns)
        ctx['total_iocs'] = IOC.objects.filter(is_active=True).count()
        return ctx


# ============================================================
# THREAT ACTORS
# ============================================================

class ThreatActorListView(LoginRequiredMixin, ListView):
    model = ThreatActor
    template_name = 'threatintel/actor_list.html'
    context_object_name = 'actors'
    paginate_by = 40

    def get_queryset(self):
        qs = ThreatActor.objects.all().annotate(
            tech_count=Count('techniques', distinct=True),
            ioc_count=Count('iocs', distinct=True),
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(attack_id__icontains=q))
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['total_count'] = ThreatActor.objects.count()
        return ctx


class ThreatActorDetailView(LoginRequiredMixin, DetailView):
    model = ThreatActor
    template_name = 'threatintel/actor_detail.html'
    context_object_name = 'actor'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['techniques'] = self.object.techniques.select_related().prefetch_related('tactics').all()
        ctx['iocs'] = self.object.iocs.filter(is_active=True)[:30]
        return ctx
