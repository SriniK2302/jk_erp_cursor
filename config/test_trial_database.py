from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from config.trial_database import copy_user_from_live


@override_settings(LIVE_POSTGRES_DB='jk_erp_live')
class CopyUserFromLiveTests(TestCase):
    databases = {'default'}

    @patch('config.trial_database._postgres_connect')
    def test_copy_user_from_live_creates_trial_user(self, connect):
        User = get_user_model()
        live_user = User.objects.create_user(username='srini', password='live-pass')
        live_user.is_superuser = True
        live_user.is_staff = True
        live_user.save()

        cursor = MagicMock()
        cursor.fetchone.return_value = (
            live_user.username,
            live_user.password,
            live_user.email,
            live_user.is_superuser,
            live_user.is_staff,
            live_user.is_active,
            live_user.first_name,
            live_user.last_name,
            live_user.last_login,
            live_user.date_joined,
        )
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = conn

        message = copy_user_from_live('srini')
        self.assertIn("trial user 'srini'", message)
        trial_user = User.objects.get(username='srini')
        self.assertEqual(trial_user.password, live_user.password)
        self.assertTrue(trial_user.is_superuser)

    @patch('config.trial_database._postgres_connect')
    def test_copy_user_missing_on_live_raises(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = conn

        with self.assertRaisesMessage(ValueError, "not found in live database"):
            copy_user_from_live('srini')
