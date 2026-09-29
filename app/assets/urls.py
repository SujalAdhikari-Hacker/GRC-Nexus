from django.urls import path
from .views import (
    AssetListView, AssetDetailView,
    AssetClassificationView, AssetOwnersView,
)

app_name = 'assets'

urlpatterns = [
    path('', AssetListView.as_view(), name='list'),
    path('by-classification/', AssetClassificationView.as_view(), name='classification'),
    path('by-owner/', AssetOwnersView.as_view(), name='owners'),
    path('<int:pk>/', AssetDetailView.as_view(), name='detail'),
]
