from django.urls import path
from .views import ControlListView, ControlDetailView

app_name = 'controls'

urlpatterns = [
    path('', ControlListView.as_view(), name='list'),
    path('<int:pk>/', ControlDetailView.as_view(), name='detail'),
]