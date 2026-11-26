from django.apps import AppConfig
from django.db.models.signals import m2m_changed


class FrameworksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'frameworks'

    def ready(self):
        from controls.models import Control

        from .propagation import link

        def on_framework_controls_changed(sender, instance, action, pk_set, reverse, **kwargs):
            """A control linked to a requirement also proposes its equivalents."""
            if action != 'post_add' or not pk_set:
                return

            from .models import FrameworkControl

            if reverse:
                requirement = instance
                for control in Control.objects.filter(pk__in=pk_set):
                    link(control, requirement)
            else:
                for requirement in FrameworkControl.objects.filter(
                    pk__in=pk_set
                ).select_related('framework'):
                    link(instance, requirement)

        m2m_changed.connect(
            on_framework_controls_changed,
            sender=Control.framework_controls.through,
            dispatch_uid='frameworks.auto_link_mappings',
            weak=False,  # the handler is local, so keep a strong reference
        )
