from django.urls import path
from .views import (
    VendorListView, VendorDetailView, VendorAssessmentCreateView
)

app_name = 'vendors'

urlpatterns = [
    path('', VendorListView.as_view(), name='list'),
    path('<int:pk>/', VendorDetailView.as_view(), name='detail'),
    path('<int:vendor_pk>/assessments/new/', VendorAssessmentCreateView.as_view(), name='assessment_create'),
]
