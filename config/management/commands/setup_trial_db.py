from django.conf import settings
from django.core.management.base import BaseCommand

from config.trial_database import provision_trial_database, trial_database_name


class Command(BaseCommand):
    help = 'Create the trial PostgreSQL database (if needed) and run migrations.'

    def handle(self, *args, **options):
        if not settings.JK_ERP_IS_TRIAL:
            self.stderr.write(
                self.style.ERROR(
                    'Set JK_ERP_ENV=trial before running setup_trial_db '
                    '(see run_jk_erp_trial.bat).'
                )
            )
            return

        self.stdout.write(f'Trial database: {trial_database_name()}')
        output = provision_trial_database()
        if output:
            self.stdout.write(output)
        self.stdout.write(
            self.style.SUCCESS(
                'Trial database is ready. Copy user srini from Setup → Server environment.'
            )
        )
