from django.urls import path
from .views import (
    FrameworkListView, FrameworkDetailView, ComplianceStatusView,
)

app_name = 'frameworks'

urlpatterns = [
    path('', FrameworkListView.as_view(), name='list'),
    path('status/', ComplianceStatusView.as_view(), name='compliance_status'),
    path('<int:pk>/', FrameworkDetailView.as_view(), name='detail'),
]
