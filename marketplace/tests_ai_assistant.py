import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from marketplace.models import Skill


class AIRequestAssistTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='aiuser', password='pw')
        Skill.objects.create(name='Django')
        Skill.objects.create(name='Python')
        self.url = reverse('ai_request_assist')

    def test_ai_request_assist_requires_login(self):
        response = self.client.post(
            self.url,
            data=json.dumps({'title': 'Need API help', 'description': 'Cannot serialize datetime in DRF'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    @override_settings(GEMINI_API_KEY='')
    def test_ai_request_assist_returns_503_when_api_key_missing(self):
        self.client.login(username='aiuser', password='pw')
        response = self.client.post(
            self.url,
            data=json.dumps({'title': 'Need API help', 'description': 'Cannot serialize datetime in DRF'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['ok'])
        self.assertIn('GEMINI_API_KEY', response.json()['error'])

    @patch('marketplace.views.generate_request_assistance')
    def test_ai_request_assist_returns_normalized_suggestions(self, mock_generate):
        mock_generate.return_value = {
            'improved_title': 'DRF serializer fails for datetime objects',
            'improved_description': 'Context, issue, expected output, and attempted fixes.',
            'suggested_tags': ['drf', 'serialization', 'datetime'],
            'suggested_skill': 'Django',
            'reasoning_summary': 'Clarified technical scope and likely troubleshooting path.',
        }
        self.client.login(username='aiuser', password='pw')

        response = self.client.post(
            self.url,
            data=json.dumps({'title': 'Need API help', 'description': 'Cannot serialize datetime in DRF'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['suggestion']['suggested_skill'], 'Django')
        self.assertEqual(payload['suggestion']['suggested_tags'], ['drf', 'serialization', 'datetime'])
        mock_generate.assert_called_once()

    def test_ai_request_assist_rejects_invalid_json(self):
        self.client.login(username='aiuser', password='pw')
        response = self.client.post(
            self.url,
            data='{bad json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
