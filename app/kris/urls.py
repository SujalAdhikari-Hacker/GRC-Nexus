from django.urls import path
from .views import KRIListView, KRIDetailView, KRICreateView, KRIUpdateView, KRIDeleteView

app_name = 'kris'

urlpatterns = [
    path('', KRIListView.as_view(), name='list'),
    path('new/', KRICreateView.as_view(), name='create'),
    path('<int:pk>/', KRIDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', KRIUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', KRIDeleteView.as_view(), name='delete'),
]
