from django.urls import path
from .views import (
    AuditListView, AuditDetailView, AuditCreateView, AuditUpdateView, AuditTimelineView,
    EvidenceListView, EvidenceDetailView, EvidenceCreateView, EvidenceUpdateView,
    EvidenceScoreCreateView, EvidenceScoreUpdateView, EvidenceScoreListView,
    ControlTestListView, ControlTestCreateView, ControlTestUpdateView,
    FindingListView, FindingDetailView, FindingCreateView, FindingUpdateView,
)

app_name = 'audits'

urlpatterns = [
    path('', AuditListView.as_view(), name='list'),
    path('timeline/', AuditTimelineView.as_view(), name='timeline'),
    path('new/', AuditCreateView.as_view(), name='create'),
    path('<int:pk>/', AuditDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', AuditUpdateView.as_view(), name='update'),

    path('evidence/', EvidenceListView.as_view(), name='evidence_list'),
    path('evidence/new/', EvidenceCreateView.as_view(), name='evidence_create'),
    path('evidence/<int:pk>/', EvidenceDetailView.as_view(), name='evidence_detail'),
    path('evidence/<int:pk>/edit/', EvidenceUpdateView.as_view(), name='evidence_update'),
    path('evidence/<int:evidence_pk>/score/new/', EvidenceScoreCreateView.as_view(), name='evidence_score_create'),
    path('evidence/score/<int:pk>/edit/', EvidenceScoreUpdateView.as_view(), name='evidence_score_update'),

    path('scoring/', EvidenceScoreListView.as_view(), name='score_list'),

    path('tests/', ControlTestListView.as_view(), name='test_list'),
    path('tests/new/', ControlTestCreateView.as_view(), name='test_create'),
    path('tests/<int:pk>/edit/', ControlTestUpdateView.as_view(), name='test_update'),

    path('findings/', FindingListView.as_view(), name='finding_list'),
    path('findings/new/', FindingCreateView.as_view(), name='finding_create'),
    path('findings/<int:pk>/', FindingDetailView.as_view(), name='finding_detail'),
    path('findings/<int:pk>/edit/', FindingUpdateView.as_view(), name='finding_update'),
]
