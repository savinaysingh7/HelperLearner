from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import HelpRequest
import time

User = get_user_model()


class HelpRequestModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='pw')

    def test_updated_at_changes_on_save(self):
        req = HelpRequest.objects.create(title='T', description='D', user=self.user, kp_bounty=5)
        old = req.updated_at
        time.sleep(0.01)
        req.title = 'T2'
        req.save()
        self.assertNotEqual(old, req.updated_at)

    def test_kp_bounty_minimum_enforced(self):
        req = HelpRequest(title='Bad', description='D', user=self.user, kp_bounty=0)
        with self.assertRaises(ValidationError):
            req.full_clean()


class RateLimitTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='rluser', password='pw')
        self.client.login(username='rluser', password='pw')

    def test_create_request_rate_limit(self):
        url = reverse('create_request')
        data = {'title': 'T', 'description': 'D', 'skill_needed': '', 'kp_bounty': 1}
        # Hit the endpoint quickly to trigger rate limit (configured 10/min)
        for i in range(11):
            res = self.client.post(url, data)
        self.assertIn(res.status_code, (429, 403))


class AccountsFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_and_edit_profile(self):
        url = reverse('signup')
        data = {'username': 'new', 'password1': 'complexpassword123', 'password2': 'complexpassword123', 'email': 'a@b.com'}
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, 302)
        user = User.objects.get(username='new')

        # Edit profile
        self.client.login(username='new', password='complexpassword123')
        edit_url = reverse('edit_profile')
        res2 = self.client.post(edit_url, {'email': 'updated@b.com', 'bio': 'hi'})
        self.assertEqual(res2.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.email, 'updated@b.com')
