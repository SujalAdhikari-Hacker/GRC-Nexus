from django.urls import path
from .views import (
    AuditListView, AuditDetailView, AuditCreateView, AuditUpdateView, AuditTimelineView,
    AuditReportView,
    EvidenceListView, EvidenceDetailView, EvidenceCreateView, EvidenceUpdateView,
    EvidenceScoreCreateView, EvidenceScoreUpdateView, EvidenceScoreListView,
    ControlTestListView, ControlTestCreateView, ControlTestUpdateView,
    FindingListView, FindingDetailView, FindingCreateView, FindingUpdateView,
    ActionItemListView, ActionItemDetailView, ActionItemCreateView, ActionItemUpdateView,
    action_mark_complete, finding_verify,
)

app_name = 'audits'

urlpatterns = [
    # Static paths first — no conflicts with <int:pk>
    path('', AuditListView.as_view(), name='list'),
    path('timeline/', AuditTimelineView.as_view(), name='timeline'),
    path('new/', AuditCreateView.as_view(), name='create'),
    path('evidence/', EvidenceListView.as_view(), name='evidence_list'),
    path('evidence/new/', EvidenceCreateView.as_view(), name='evidence_create'),
    path('scoring/', EvidenceScoreListView.as_view(), name='score_list'),
    path('tests/', ControlTestListView.as_view(), name='test_list'),
    path('tests/new/', ControlTestCreateView.as_view(), name='test_create'),
    path('findings/', FindingListView.as_view(), name='finding_list'),
    path('findings/new/', FindingCreateView.as_view(), name='finding_create'),
    path('actions/', ActionItemListView.as_view(), name='action_list'),
    path('actions/new/', ActionItemCreateView.as_view(), name='action_create'),

    # Detail sub-paths for a single audit — MUST come before bare <int:pk>/
    path('<int:pk>/report/', AuditReportView.as_view(), name='audit_report'),
    path('<int:pk>/edit/', AuditUpdateView.as_view(), name='update'),
    path('<int:pk>/', AuditDetailView.as_view(), name='detail'),

    # Evidence detail routes
    path('evidence/<int:pk>/', EvidenceDetailView.as_view(), name='evidence_detail'),
    path('evidence/<int:pk>/edit/', EvidenceUpdateView.as_view(), name='evidence_update'),
    path('evidence/<int:evidence_pk>/score/new/', EvidenceScoreCreateView.as_view(), name='evidence_score_create'),
    path('evidence/score/<int:pk>/edit/', EvidenceScoreUpdateView.as_view(), name='evidence_score_update'),

    # Test routes
    path('tests/<int:pk>/edit/', ControlTestUpdateView.as_view(), name='test_update'),

    # Finding routes
    path('findings/<int:pk>/', FindingDetailView.as_view(), name='finding_detail'),
    path('findings/<int:pk>/edit/', FindingUpdateView.as_view(), name='finding_update'),
    path('findings/<int:pk>/verify/', finding_verify, name='finding_verify'),

    # Action routes
    path('actions/<int:pk>/', ActionItemDetailView.as_view(), name='action_detail'),
    path('actions/<int:pk>/edit/', ActionItemUpdateView.as_view(), name='action_update'),
    path('actions/<int:pk>/complete/', action_mark_complete, name='action_complete'),
]
