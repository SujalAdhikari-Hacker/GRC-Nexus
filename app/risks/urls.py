from django.urls import path
from .views import (
    RiskListView, RiskDetailView, RiskCreateView, RiskUpdateView,
    risk_score_preview,
    RiskTreatmentCreateView, RiskTreatmentUpdateView,
    RiskAppetiteListView, RiskAppetiteCreateView, RiskAppetiteUpdateView,
)

app_name = 'risks'

urlpatterns = [
    path('', RiskListView.as_view(), name='list'),
    path('new/', RiskCreateView.as_view(), name='create'),
    path('score-preview/', risk_score_preview, name='score_preview'),

    path('appetite/', RiskAppetiteListView.as_view(), name='appetite_list'),
    path('appetite/new/', RiskAppetiteCreateView.as_view(), name='appetite_create'),
    path('appetite/<int:pk>/edit/', RiskAppetiteUpdateView.as_view(), name='appetite_update'),

    path('<int:risk_pk>/treatments/new/', RiskTreatmentCreateView.as_view(), name='treatment_create'),
    path('treatments/<int:pk>/edit/', RiskTreatmentUpdateView.as_view(), name='treatment_update'),

    path('<int:pk>/', RiskDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', RiskUpdateView.as_view(), name='update'),
]
