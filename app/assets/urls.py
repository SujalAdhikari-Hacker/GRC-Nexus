from django.urls import path
from .views import AssetListView, AssetDetailView

app_name = 'assets'

urlpatterns = [
    path('', AssetListView.as_view(), name='list'),
    path('<int:pk>/', AssetDetailView.as_view(), name='detail'),
]