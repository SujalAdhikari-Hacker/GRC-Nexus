from django.urls import path
from .views import (
    FrameworkListView, FrameworkDetailView, ComplianceStatusView,
    ComplianceAssessmentListView, ComplianceAssessmentDetailView,
    ComplianceAssessmentCreateView, ComplianceAssessmentUpdateView,
    ComplianceAssessmentItemUpdateView, assessment_item_quick_status,
    FrameworkCreateView, FrameworkUpdateView,
    FrameworkControlCreateView, FrameworkControlUpdateView,
)

app_name = 'frameworks'

urlpatterns = [
    path('', FrameworkListView.as_view(), name='list'),
    path('new/', FrameworkCreateView.as_view(), name='create'),
    path('status/', ComplianceStatusView.as_view(), name='compliance_status'),

    # Framework control routes
    path('controls/new/', FrameworkControlCreateView.as_view(), name='control_create'),
    path('controls/<int:pk>/edit/', FrameworkControlUpdateView.as_view(), name='control_update'),

    # Compliance assessments
    path('assessments/', ComplianceAssessmentListView.as_view(), name='assessment_list'),
    path('assessments/new/', ComplianceAssessmentCreateView.as_view(), name='assessment_create'),
    path('assessments/items/<int:pk>/edit/', ComplianceAssessmentItemUpdateView.as_view(), name='assessment_item_update'),
    path('assessments/items/<int:pk>/status/', assessment_item_quick_status, name='assessment_item_status'),
    path('assessments/<int:pk>/', ComplianceAssessmentDetailView.as_view(), name='assessment_detail'),
    path('assessments/<int:pk>/edit/', ComplianceAssessmentUpdateView.as_view(), name='assessment_update'),

    # Framework detail routes (must come AFTER static paths)
    path('<int:pk>/edit/', FrameworkUpdateView.as_view(), name='update'),
    path('<int:pk>/', FrameworkDetailView.as_view(), name='detail'),
]
