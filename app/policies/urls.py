from django.urls import path
from .views import (
    PolicyListView, PolicyDetailView,
    PolicyCreateView, PolicyUpdateView,
)

app_name = 'policies'

urlpatterns = [
    path('', PolicyListView.as_view(), name='list'),
    path('new/', PolicyCreateView.as_view(), name='create'),
    path('<int:pk>/', PolicyDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', PolicyUpdateView.as_view(), name='update'),
]
