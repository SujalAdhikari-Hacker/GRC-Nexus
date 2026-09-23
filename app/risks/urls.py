from django.urls import path
from .views import (
    RiskListView, RiskDetailView, RiskCreateView, RiskUpdateView,
    risk_score_preview,
)

app_name = 'risks'

urlpatterns = [
    path('', RiskListView.as_view(), name='list'),
    path('new/', RiskCreateView.as_view(), name='create'),
    path('<int:pk>/', RiskDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', RiskUpdateView.as_view(), name='update'),
    path('score-preview/', risk_score_preview, name='score_preview'),
]