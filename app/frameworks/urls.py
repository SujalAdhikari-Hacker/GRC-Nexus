from django.urls import path
from .views import (
    FrameworkListView, FrameworkDetailView, ComplianceStatusView,
    ComplianceAssessmentListView, ComplianceAssessmentDetailView,
    ComplianceAssessmentCreateView, ComplianceAssessmentUpdateView,
    ComplianceAssessmentItemUpdateView, assessment_item_quick_status,
)

app_name = 'frameworks'

urlpatterns = [
    path('', FrameworkListView.as_view(), name='list'),
    path('status/', ComplianceStatusView.as_view(), name='compliance_status'),

    path('assessments/', ComplianceAssessmentListView.as_view(), name='assessment_list'),
    path('assessments/new/', ComplianceAssessmentCreateView.as_view(), name='assessment_create'),
    path('assessments/items/<int:pk>/edit/', ComplianceAssessmentItemUpdateView.as_view(), name='assessment_item_update'),
    path('assessments/items/<int:pk>/status/', assessment_item_quick_status, name='assessment_item_status'),
    path('assessments/<int:pk>/', ComplianceAssessmentDetailView.as_view(), name='assessment_detail'),
    path('assessments/<int:pk>/edit/', ComplianceAssessmentUpdateView.as_view(), name='assessment_update'),

    path('<int:pk>/', FrameworkDetailView.as_view(), name='detail'),
]
