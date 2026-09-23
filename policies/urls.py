from django.urls import path
from .views import PolicyListView, PolicyDetailView

app_name = 'policies'

urlpatterns = [
    path('', PolicyListView.as_view(), name='list'),
    path('<int:pk>/', PolicyDetailView.as_view(), name='detail'),
]