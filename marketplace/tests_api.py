from rest_framework.test import APIClient, APITestCase

from accounts.models import CustomUser

from .models import Comment, HelpRequest, Rating, Skill


class ExpandedApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.skill_python = Skill.objects.create(name='Python')
        self.skill_django = Skill.objects.create(name='Django')

        self.poster = CustomUser.objects.create_user(username='poster', password='pw', knowledge_points=80)
        self.helper = CustomUser.objects.create_user(username='helper', password='pw', knowledge_points=150)
        self.other = CustomUser.objects.create_user(username='other', password='pw', knowledge_points=60)

        self.helper.skills.add(self.skill_python)

        self.open_request = HelpRequest.objects.create(
            title='Open API request',
            description='Need help',
            user=self.poster,
            skill_needed=self.skill_python,
            kp_bounty=8,
            status='open',
        )
        self.resolved_request = HelpRequest.objects.create(
            title='Resolved API request',
            description='Done',
            user=self.poster,
            skill_needed=self.skill_django,
            kp_bounty=12,
            status='resolved',
            accepted_by=self.helper,
        )
        Rating.objects.create(
            request=self.resolved_request,
            given_by=self.poster,
            given_to=self.helper,
            score=5,
        )

        Comment.objects.create(request=self.open_request, user=self.poster, content='Public note', is_private=False)
        Comment.objects.create(request=self.open_request, user=self.poster, content='Private note', is_private=True)

    def test_users_endpoint_returns_paginated_users_with_rating_and_skills(self):
        response = self.client.get('/api/users/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)

        helper_payload = next(item for item in response.data['results'] if item['username'] == 'helper')
        self.assertEqual(helper_payload['knowledge_points'], 150)
        self.assertIn('Python', helper_payload['skills'])
        self.assertEqual(helper_payload['avg_rating'], 5.0)

    def test_skills_endpoint_returns_request_counts(self):
        response = self.client.get('/api/skills/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)

        python_payload = next(item for item in response.data['results'] if item['name'] == 'Python')
        django_payload = next(item for item in response.data['results'] if item['name'] == 'Django')

        self.assertEqual(python_payload['request_count'], 1)
        self.assertEqual(django_payload['request_count'], 1)

    def test_requests_filtering_and_public_comments_endpoint(self):
        response = self.client.get('/api/requests/', {'status': 'open', 'skill': self.skill_python.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.open_request.pk)

        comments_response = self.client.get(f'/api/requests/{self.open_request.pk}/comments/')
        self.assertEqual(comments_response.status_code, 200)
        self.assertEqual(len(comments_response.data['results']), 1)
        self.assertEqual(comments_response.data['results'][0]['content'], 'Public note')
