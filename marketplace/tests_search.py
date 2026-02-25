from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import HelpRequest, Skill, Tag


class UnifiedSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.skill = Skill.objects.create(name='Django')
        self.tag = Tag.objects.create(name='django')
        self.poster = CustomUser.objects.create_user(username='django_helper', password='pw')
        self.request_obj = HelpRequest.objects.create(
            title='Django forms issue',
            description='Need help with form validation.',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='open',
        )
        self.request_obj.tags.add(self.tag)

    def test_search_page_shows_grouped_results_with_highlighting(self):
        response = self.client.get(reverse('search'), {'q': 'django'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Requests (1)')
        self.assertContains(response, 'Users (1)')
        self.assertContains(response, 'Skills (1)')
        self.assertContains(response, '<mark>Django</mark>', html=False)

    def test_search_page_empty_query_shows_prompt(self):
        response = self.client.get(reverse('search'), {'q': ''})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a keyword in the navbar search')
        self.assertNotContains(response, 'No results found')

    def test_api_search_returns_cross_model_grouped_results(self):
        response = self.client.get(reverse('api-search'), {'q': 'django'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('requests', response.json())
        self.assertIn('users', response.json())
        self.assertIn('skills', response.json())
        self.assertGreaterEqual(len(response.json()['requests']), 1)
        self.assertGreaterEqual(len(response.json()['users']), 1)
        self.assertGreaterEqual(len(response.json()['skills']), 1)
