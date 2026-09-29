from django.urls import path
from .views import (
    AssetListView, AssetDetailView,
    AssetClassificationView, AssetOwnersView,
    AssetExplorerPickerView, AssetExplorerView,
    AssetCreateView, AssetUpdateView,
)

app_name = 'assets'

urlpatterns = [
    path('', AssetListView.as_view(), name='list'),
    path('new/', AssetCreateView.as_view(), name='create'),
    path('by-classification/', AssetClassificationView.as_view(), name='classification'),
    path('by-owner/', AssetOwnersView.as_view(), name='owners'),
    path('explorer/', AssetExplorerPickerView.as_view(), name='explorer_picker'),
    path('<int:pk>/', AssetDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', AssetUpdateView.as_view(), name='update'),
    path('<int:pk>/explorer/', AssetExplorerView.as_view(), name='explorer'),
]
