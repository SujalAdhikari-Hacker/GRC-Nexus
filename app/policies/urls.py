from django.urls import path
from .views import (
    PolicyListView, PolicyDetailView,
    PolicyCreateView, PolicyUpdateView, PolicyDeleteView,
    PolicyAttestView, PolicyTransitionView,
)

app_name = 'policies'

urlpatterns = [
    path('', PolicyListView.as_view(), name='list'),
    path('new/', PolicyCreateView.as_view(), name='create'),
    path('<int:pk>/', PolicyDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', PolicyUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', PolicyDeleteView.as_view(), name='delete'),
    path('<int:pk>/attest/', PolicyAttestView.as_view(), name='attest'),
    path('<int:pk>/transition/', PolicyTransitionView.as_view(), name='transition'),
]
