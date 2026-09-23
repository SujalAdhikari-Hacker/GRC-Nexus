from django.urls import path
from .views import DashboardView, global_search

app_name = 'core'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('search/', global_search, name='search'),
]