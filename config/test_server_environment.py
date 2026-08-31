from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    JK_ERP_IS_TRIAL=False,
    TRIAL_ALLOWED_USERNAME='srini',
    LIVE_POSTGRES_DB='jk_erp',
)
class ServerEnvironmentPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.srini = User.objects.create_user(username='srini', password='pass')
        self.other = User.objects.create_user(username='bob', password='pass')

    def test_srini_can_open_server_page(self):
        self.client.force_login(self.srini)
        response = self.client.get(reverse('setup_server_environment'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Live server')
        self.assertContains(response, 'Trial server')

    def test_other_user_cannot_open_server_page(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('setup_server_environment'))
        self.assertEqual(response.status_code, 403)

    def test_trial_actions_blocked_on_live_server(self):
        self.client.force_login(self.srini)
        for action in ('migrate', 'create_db', 'copy_user'):
            response = self.client.post(
                reverse('setup_server_environment'),
                {'action': action},
            )
            self.assertRedirects(response, reverse('setup_server_environment'))
        follow = self.client.get(reverse('setup_server_environment'))
        self.assertContains(
            follow,
            'Trial database actions are only available on the trial server.',
        )


@override_settings(
    JK_ERP_IS_TRIAL=True,
    TRIAL_ALLOWED_USERNAME='srini',
    LIVE_POSTGRES_DB='jk_erp',
)
class TrialServerActionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.srini = User.objects.create_user(username='srini', password='pass')

    @patch('config.views.server_environment.run_migrations', return_value='Applied migrations.')
    @patch(
        'config.views.server_environment.migration_status',
        return_value={
            'trial_db_ready': True,
            'trial_db_error': None,
            'database_name': 'jk_erp_trial',
            'live_database_name': 'jk_erp',
            'pending_migrations': [],
            'pending_count': 0,
        },
    )
    def test_run_migrations_on_trial(self, _status, run_migrations):
        self.client.force_login(self.srini)
        response = self.client.post(
            reverse('setup_server_environment'),
            {'action': 'migrate'},
        )
        self.assertRedirects(response, reverse('setup_server_environment'))
        run_migrations.assert_called_once()
        follow = self.client.get(reverse('setup_server_environment'))
        self.assertContains(follow, 'Applied migrations.')

    @patch(
        'config.views.server_environment.provision_trial_database',
        return_value='Created database jk_erp_trial.',
    )
    def test_create_trial_database(self, provision):
        self.client.force_login(self.srini)
        response = self.client.post(
            reverse('setup_server_environment'),
            {'action': 'create_db'},
        )
        self.assertRedirects(response, reverse('setup_server_environment'))
        provision.assert_called_once()
        follow = self.client.get(reverse('setup_server_environment'))
        self.assertContains(follow, 'Created database jk_erp_trial.')

    @patch(
        'config.views.server_environment.copy_user_from_live',
        return_value='Updated trial user srini from live database.',
    )
    @patch(
        'config.views.server_environment.migration_status',
        return_value={
            'trial_db_ready': True,
            'trial_db_error': None,
            'database_name': 'jk_erp_trial',
            'live_database_name': 'jk_erp',
            'pending_migrations': [],
            'pending_count': 0,
        },
    )
    def test_copy_user_from_live(self, _status, copy_user):
        self.client.force_login(self.srini)
        response = self.client.post(
            reverse('setup_server_environment'),
            {'action': 'copy_user'},
        )
        self.assertRedirects(response, reverse('setup_server_environment'))
        copy_user.assert_called_once_with('srini')
        follow = self.client.get(reverse('setup_server_environment'))
        self.assertContains(follow, 'Updated trial user srini')
