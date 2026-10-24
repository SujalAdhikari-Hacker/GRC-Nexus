"""Flag accounts that are still using a known seeded password.

Run once after deploying the MFA/password-rotation release. Affected users
are forced through the password-change screen on their next sign-in; no
password is printed or stored by this command.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Flag active users whose password is still a known demo default.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default='demo1234',
            help='Known default password to detect (default: demo1234).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report affected accounts without saving changes.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        password = options['password']
        dry_run = options['dry_run']
        affected = []
        for user in User.objects.filter(is_active=True).iterator():
            if user.check_password(password):
                affected.append(user)
                if not dry_run and not user.must_change_password:
                    user.must_change_password = True
                    user.save(update_fields=['must_change_password'])

        verb = 'Would flag' if dry_run else 'Flagged'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {len(affected)} account(s) for mandatory password rotation.'
        ))
        for user in affected:
            self.stdout.write(f'  - {user.get_username()}')
