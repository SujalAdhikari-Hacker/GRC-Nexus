from django.urls import path
from .views import (
    ControlListView, ControlDetailView,
    ControlCreateView, ControlUpdateView,
    ControlEvidenceCreateView, ControlFrameworkMappingCreateView,
)

app_name = 'controls'

urlpatterns = [
    path('', ControlListView.as_view(), name='list'),
    path('new/', ControlCreateView.as_view(), name='create'),
    path('<int:pk>/', ControlDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', ControlUpdateView.as_view(), name='update'),
    path('<int:control_pk>/evidence/new/', ControlEvidenceCreateView.as_view(), name='evidence_create'),
    path('<int:control_pk>/mapping/new/', ControlFrameworkMappingCreateView.as_view(), name='mapping_create'),
]
