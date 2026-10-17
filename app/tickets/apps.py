from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tickets'

    def ready(self):
        import tickets.signals       # noqa: F401  (registers post_save receivers)
        import tickets.login_signal  # noqa: F401  (registers the login receiver)
