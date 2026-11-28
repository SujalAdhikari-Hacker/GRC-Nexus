from django.urls import path
from .views import (
    ThreatIntelOverviewView,
    IOCFeedView, IOCDetailView,
    AttackMatrixView,
    ThreatActorListView, ThreatActorDetailView,
    sync_attack_view,
)

app_name = 'threatintel'

urlpatterns = [
    path('', ThreatIntelOverviewView.as_view(), name='overview'),

    path('iocs/', IOCFeedView.as_view(), name='ioc_feed'),
    path('iocs/<int:pk>/', IOCDetailView.as_view(), name='ioc_detail'),

    path('attack-matrix/', AttackMatrixView.as_view(), name='attack_matrix'),
    path('sync-attack/', sync_attack_view, name='sync_attack'),

    path('actors/', ThreatActorListView.as_view(), name='actor_list'),
    path('actors/<int:pk>/', ThreatActorDetailView.as_view(), name='actor_detail'),
]
