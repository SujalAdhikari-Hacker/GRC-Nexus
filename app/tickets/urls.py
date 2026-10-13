from django.urls import path

from .views import (
    TicketListView, MyTicketsView, AvailableTicketsView,
    TicketDetailView, TicketCreateView, TicketUpdateView,
    ticket_claim, ticket_assign, ticket_update_status, ticket_add_comment,
)

app_name = 'tickets'

urlpatterns = [
    path('', TicketListView.as_view(), name='list'),
    path('mine/', MyTicketsView.as_view(), name='my_tickets'),
    path('available/', AvailableTicketsView.as_view(), name='available'),
    path('new/', TicketCreateView.as_view(), name='create'),
    path('<int:pk>/', TicketDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', TicketUpdateView.as_view(), name='update'),
    path('<int:pk>/claim/', ticket_claim, name='claim'),
    path('<int:pk>/assign/', ticket_assign, name='assign'),
    path('<int:pk>/status/', ticket_update_status, name='update_status'),
    path('<int:pk>/comment/', ticket_add_comment, name='add_comment'),
]