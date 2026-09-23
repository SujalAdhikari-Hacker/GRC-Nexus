from django.urls import path
from .views import (
    ControlListView, ControlDetailView, ControlEvidenceCreateView
)

app_name = 'controls'

urlpatterns = [
    path('', ControlListView.as_view(), name='list'),
    path('<int:pk>/', ControlDetailView.as_view(), name='detail'),
    path('<int:control_pk>/evidence/new/', ControlEvidenceCreateView.as_view(), name='evidence_create'),
]
