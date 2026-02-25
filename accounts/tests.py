from django.test import TestCase, Client
from django.urls import reverse
from .models import CustomUser


class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='password123',
            email='test@example.com',
            bio='Original Bio'
        )

    def test_signup_success(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'bio': 'I am new here',
            'password1': 'N3wSecurePass!2026',
            'password2': 'N3wSecurePass!2026'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(username='newuser').exists())

    def test_signup_rejects_weak_password(self):
        response = self.client.post(reverse('signup'), {
            'username': 'weakuser',
            'email': 'weak@example.com',
            'password1': '12345678',
            'password2': '12345678',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='weakuser').exists())

    def test_profile_view_authenticated(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'testuser')

    def test_profile_view_unauthenticated(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_edit_profile_success(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(reverse('edit_profile'), {
            'email': 'updated@example.com',
            'bio': 'Updated Bio'
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.bio, 'Updated Bio')

    def test_edit_profile_requires_login(self):
        response = self.client.get(reverse('edit_profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])
