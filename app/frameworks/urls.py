from django.urls import path
from .views import FrameworkListView, FrameworkDetailView

app_name = 'frameworks'

urlpatterns = [
    path('', FrameworkListView.as_view(), name='list'),
    path('<int:pk>/', FrameworkDetailView.as_view(), name='detail'),
]