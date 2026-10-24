from django.apps import AppConfig
from django.db import connection
from django.db.models.signals import post_migrate
from django.dispatch import receiver


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.settings_model  # noqa
        import core.notification_signals  # noqa


@receiver(post_migrate)
def install_row_level_security(sender, **kwargs):
    """Re-apply RLS after every migration run.

    The dedicated ``core.0011`` migration handles the existing database, but
    a fresh database may create business tables after that migration. Running
    the idempotent installer once all apps have migrated guarantees every
    scoped table gets a policy.
    """
    if getattr(sender, 'label', None) != 'core':
        return
    if connection.vendor != 'postgresql':
        return

    # Do not swallow failures: a deployment that cannot install its RLS
    # backstop should fail the migration instead of starting unprotected.
    from core.rls import apply_rls

    apply_rls(connection=connection)
