from django.urls import path
from .views import (
    RiskListView, RiskDetailView, RiskCreateView, RiskUpdateView,
    risk_score_preview, RiskMatrixView,
    RiskTreatmentCreateView, RiskTreatmentUpdateView, TreatmentListView,
    RiskAppetiteListView, RiskAppetiteCreateView, RiskAppetiteUpdateView,
    RiskExceptionListView, RiskExceptionDetailView,
    RiskExceptionCreateView, RiskExceptionUpdateView,
    exception_approve, exception_revoke,
)

app_name = 'risks'

urlpatterns = [
    path('', RiskListView.as_view(), name='list'),
    path('new/', RiskCreateView.as_view(), name='create'),
    path('score-preview/', risk_score_preview, name='score_preview'),
    path('matrix/', RiskMatrixView.as_view(), name='matrix'),

    path('treatments/', TreatmentListView.as_view(), name='treatment_list'),
    path('<int:risk_pk>/treatments/new/', RiskTreatmentCreateView.as_view(), name='treatment_create'),
    path('treatments/<int:pk>/edit/', RiskTreatmentUpdateView.as_view(), name='treatment_update'),

    path('appetite/', RiskAppetiteListView.as_view(), name='appetite_list'),
    path('appetite/new/', RiskAppetiteCreateView.as_view(), name='appetite_create'),
    path('appetite/<int:pk>/edit/', RiskAppetiteUpdateView.as_view(), name='appetite_update'),

    path('exceptions/', RiskExceptionListView.as_view(), name='exception_list'),
    path('exceptions/new/', RiskExceptionCreateView.as_view(), name='exception_create'),
    path('exceptions/<int:pk>/', RiskExceptionDetailView.as_view(), name='exception_detail'),
    path('exceptions/<int:pk>/edit/', RiskExceptionUpdateView.as_view(), name='exception_update'),
    path('exceptions/<int:pk>/approve/', exception_approve, name='exception_approve'),
    path('exceptions/<int:pk>/revoke/', exception_revoke, name='exception_revoke'),

    path('<int:pk>/', RiskDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', RiskUpdateView.as_view(), name='update'),
]
