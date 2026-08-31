from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(JK_ERP_IS_TRIAL=True, TRIAL_ALLOWED_USERNAME='srini')
class TrialServerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.srini = User.objects.create_user(username='srini', password='pass')
        self.other = User.objects.create_user(username='bob', password='pass')

    def test_login_rejects_other_users_on_trial(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'bob', 'password': 'pass'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'This trial server is only available to authorized users.',
        )

    def test_login_allows_srini_on_trial(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'srini', 'password': 'pass'},
        )
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)

    def test_middleware_logs_out_other_users_on_trial(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('login'))
        follow_up = self.client.get(reverse('home'))
        self.assertEqual(follow_up.status_code, 302)
        self.assertTrue(follow_up.url.startswith(reverse('login')))


@override_settings(JK_ERP_IS_TRIAL=False)
class ProductionServerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.bob = User.objects.create_user(username='bob', password='pass')

    def test_login_allows_any_user_on_production(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'bob', 'password': 'pass'},
        )
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
