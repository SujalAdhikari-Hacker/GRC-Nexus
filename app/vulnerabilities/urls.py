from django.urls import path
from .views import (
    FindingListView, FindingDetailView,
    VulnerabilityListView, VulnerabilityDetailView,
    enrich_vulnerability_view, cascade_finding_view,
    LiveCVEFeedView,
    ManualVulnerabilityCreateView,
)

app_name = 'vulnerabilities'

urlpatterns = [
    path('', FindingListView.as_view(), name='finding_list'),
    path('live/', LiveCVEFeedView.as_view(), name='live_feed'),
    path('manual/new/', ManualVulnerabilityCreateView.as_view(), name='manual_create'),
    path('findings/<int:pk>/', FindingDetailView.as_view(), name='finding_detail'),
    path('findings/<int:pk>/create-risk/', cascade_finding_view, name='finding_cascade'),
    path('cves/', VulnerabilityListView.as_view(), name='vulnerability_list'),
    path('cves/<int:pk>/', VulnerabilityDetailView.as_view(), name='vulnerability_detail'),
    path('cves/<int:pk>/enrich/', enrich_vulnerability_view, name='vulnerability_enrich'),
]
