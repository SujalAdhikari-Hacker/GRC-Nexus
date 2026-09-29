from django.urls import path
from .views import (
    VendorListView, VendorDetailView,
    VendorCreateView, VendorUpdateView,
    VendorAssessmentListView,
    VendorAssessmentCreateView, VendorAssessmentUpdateView, VendorAssessmentDetailView,
)

app_name = 'vendors'

urlpatterns = [
    path('', VendorListView.as_view(), name='list'),
    path('assessments/', VendorAssessmentListView.as_view(), name='assessment_list'),
    path('assessments/new/', VendorAssessmentCreateView.as_view(), name='assessment_create'),
    path('assessments/<int:pk>/', VendorAssessmentDetailView.as_view(), name='assessment_detail'),
    path('assessments/<int:pk>/edit/', VendorAssessmentUpdateView.as_view(), name='assessment_update'),
    path('new/', VendorCreateView.as_view(), name='create'),
    path('<int:pk>/', VendorDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', VendorUpdateView.as_view(), name='update'),
    path('<int:vendor_pk>/assessments/new/', VendorAssessmentCreateView.as_view(), name='assessment_create_for_vendor'),
]
