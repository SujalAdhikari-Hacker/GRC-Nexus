from django.urls import path
from .views import (
    FindingListView, FindingDetailView,
    VulnerabilityListView, VulnerabilityDetailView,
)

app_name = 'vulnerabilities'

urlpatterns = [
    path('', FindingListView.as_view(), name='finding_list'),
    path('findings/<int:pk>/', FindingDetailView.as_view(), name='finding_detail'),
    path('cves/', VulnerabilityListView.as_view(), name='vulnerability_list'),
    path('cves/<int:pk>/', VulnerabilityDetailView.as_view(), name='vulnerability_detail'),
]
