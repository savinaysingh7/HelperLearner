import time

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .forms import HelpRequestForm
from .models import HelpRequest, Skill

User = get_user_model()


class HelpRequestModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='pw')

    def test_updated_at_changes_on_save(self):
        req = HelpRequest.objects.create(title='T', description='D', user=self.user, kp_bounty=5)
        self.assertIsNotNone(req.updated_at)
        old = req.updated_at
        time.sleep(0.01)
        req.title = 'T2'
        req.save()
        self.assertNotEqual(old, req.updated_at)

    def test_kp_bounty_minimum_enforced_on_model(self):
        for invalid_bounty in (0, -5):
            with self.subTest(invalid_bounty=invalid_bounty):
                req = HelpRequest(title='Bad', description='D', user=self.user, kp_bounty=invalid_bounty)
                with self.assertRaises(ValidationError):
                    req.full_clean()

    def test_kp_bounty_minimum_enforced_on_form(self):
        skill = Skill.objects.create(name='Django')
        form = HelpRequestForm(data={
            'title': 'Bad bounty',
            'description': 'Example',
            'skill_needed': skill.id,
            'kp_bounty': 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('kp_bounty', form.errors)


class RateLimitTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.skill = Skill.objects.create(name='Python')
        self.user = User.objects.create_user(username='rluser', password='pw')
        self.client.login(username='rluser', password='pw')

    def test_create_request_rate_limit(self):
        url = reverse('create_request')
        data = {'title': 'T', 'description': 'D', 'skill_needed': self.skill.id, 'kp_bounty': 1}
        # Hit the endpoint quickly to trigger rate limit (configured 10/min)
        for i in range(11):
            res = self.client.post(url, data)
        self.assertIn(res.status_code, (429, 403))

    def test_claim_request_rate_limit(self):
        owner = User.objects.create_user(username='owner', password='pw')

        for idx in range(21):
            req = HelpRequest.objects.create(
                title=f'Task {idx}',
                description='Claim me',
                user=owner,
                skill_needed=self.skill,
                kp_bounty=1,
            )
            res = self.client.post(reverse('claim_request', args=[req.pk]))

        self.assertIn(res.status_code, (429, 403))


class AccountsFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_and_edit_profile(self):
        url = reverse('signup')
        data = {'username': 'new', 'password1': 'StrongerPass!2026', 'password2': 'StrongerPass!2026', 'email': 'a@b.com'}
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, 302)
        user = User.objects.get(username='new')

        # Edit profile
        self.client.login(username='new', password='StrongerPass!2026')
        edit_url = reverse('edit_profile')
        res2 = self.client.post(
            edit_url,
            {'email': 'updated@b.com', 'bio': 'hi', 'notification_preference': 'both'},
        )
        self.assertEqual(res2.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.email, 'updated@b.com')


class SecurityHeadersTests(TestCase):
    def test_security_headers_enabled(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')


class HealthCheckTests(TestCase):
    def test_health_check_endpoint_returns_ok_json(self):
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'service': 'helperlearner'})


class CsrfProtectionTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.skill = Skill.objects.create(name='Security')
        self.poster = User.objects.create_user(username='poster', password='pw')
        self.helper = User.objects.create_user(username='helper', password='pw')

    def test_create_request_without_csrf_token_is_rejected(self):
        self.client.login(username='poster', password='pw')
        response = self.client.post(reverse('create_request'), {
            'title': 'Need help',
            'description': 'Please assist',
            'skill_needed': self.skill.id,
            'kp_bounty': 5,
        })
        self.assertEqual(response.status_code, 403)

    def test_claim_request_without_csrf_token_is_rejected(self):
        help_request = HelpRequest.objects.create(
            title='Claimable',
            description='Try claim',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=3,
        )
        self.client.login(username='helper', password='pw')
        response = self.client.post(reverse('claim_request', args=[help_request.pk]))
        self.assertEqual(response.status_code, 403)
