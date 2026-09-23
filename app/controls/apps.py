from django.apps import AppConfig


class ControlsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'controls'

    def ready(self):
        import controls.signals  # noqa