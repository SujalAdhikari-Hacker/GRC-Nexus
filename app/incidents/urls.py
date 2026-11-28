from django.urls import path

from . import views

app_name = 'incidents'

urlpatterns = [
    path('', views.IncidentListView.as_view(), name='list'),
    path('new/', views.IncidentCreateView.as_view(), name='create'),
    path('<int:pk>/', views.IncidentDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.IncidentUpdateView.as_view(), name='update'),
    path('<int:pk>/advance/', views.IncidentAdvanceView.as_view(), name='advance'),
    path('<int:pk>/close/', views.IncidentCloseView.as_view(), name='close'),
    path('<int:pk>/raise-risk/', views.IncidentRaiseRiskView.as_view(), name='raise_risk'),
]
