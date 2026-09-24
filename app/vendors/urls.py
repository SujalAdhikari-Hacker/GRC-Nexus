from django.urls import path
from .views import (
    VendorListView, VendorDetailView, VendorAssessmentCreateView,
    VendorAssessmentListView,
)

app_name = 'vendors'

urlpatterns = [
    path('', VendorListView.as_view(), name='list'),
    path('assessments/', VendorAssessmentListView.as_view(), name='assessment_list'),
    path('<int:pk>/', VendorDetailView.as_view(), name='detail'),
    path('<int:vendor_pk>/assessments/new/', VendorAssessmentCreateView.as_view(), name='assessment_create'),
]
