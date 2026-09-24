from django.urls import path
from .views import (
    ControlListView, ControlDetailView,
    ControlCreateView, ControlUpdateView,
    ControlEvidenceCreateView, ControlFrameworkMappingCreateView,
    ControlFrameworkMatrixView,
    ControlLifecycleView, advance_lifecycle_view, regress_lifecycle_view, set_lifecycle_view,
)

app_name = 'controls'

urlpatterns = [
    path('', ControlListView.as_view(), name='list'),
    path('matrix/', ControlFrameworkMatrixView.as_view(), name='framework_matrix'),
    path('lifecycle/', ControlLifecycleView.as_view(), name='lifecycle'),
    path('new/', ControlCreateView.as_view(), name='create'),
    path('<int:pk>/', ControlDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', ControlUpdateView.as_view(), name='update'),
    path('<int:control_pk>/evidence/new/', ControlEvidenceCreateView.as_view(), name='evidence_create'),
    path('<int:control_pk>/mapping/new/', ControlFrameworkMappingCreateView.as_view(), name='mapping_create'),
    path('<int:pk>/advance/', advance_lifecycle_view, name='lifecycle_advance'),
    path('<int:pk>/regress/', regress_lifecycle_view, name='lifecycle_regress'),
    path('<int:pk>/set-lifecycle/', set_lifecycle_view, name='lifecycle_set'),
]
