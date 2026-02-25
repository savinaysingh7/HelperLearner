from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import CustomUser

from .models import HelpRequest, Rating, Skill


class TrustScoreFeatureTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(username='helper_user', password='pw', knowledge_points=120)
        self.requester = CustomUser.objects.create_user(username='requester', password='pw')
        self.third = CustomUser.objects.create_user(username='third', password='pw')
        self.skill = Skill.objects.create(name='Django')

        resolved_help = HelpRequest.objects.create(
            title='Need help',
            description='Resolved by helper',
            user=self.requester,
            skill_needed=self.skill,
            kp_bounty=10,
            status='resolved',
            accepted_by=self.user,
        )
        Rating.objects.create(
            request=resolved_help,
            given_by=self.requester,
            given_to=self.user,
            score=5,
        )

        HelpRequest.objects.create(
            title='My resolved post',
            description='Poster resolved',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=6,
            status='resolved',
            accepted_by=self.third,
        )
        HelpRequest.objects.create(
            title='My canceled post',
            description='Poster canceled',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=4,
            status='canceled',
        )

    def test_public_profile_context_contains_trust_score(self):
        response = self.client.get(reverse('public_profile', args=[self.user.username]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(hasattr(response.context['profile_user'], 'trust_score'))
        self.assertGreater(response.context['profile_user'].trust_score, 0)
        self.assertContains(response, 'Trust')

    def test_leaderboard_context_exposes_trust_scores(self):
        response = self.client.get(reverse('leaderboard'), {'tab': 'helped'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(hasattr(row, 'trust_score') for row in response.context['active_leaders']))

    def test_api_users_includes_trust_score_field(self):
        response = self.client.get('/api/users/')

        self.assertEqual(response.status_code, 200)
        payload = next(item for item in response.data['results'] if item['username'] == 'helper_user')
        self.assertIn('trust_score', payload)
        self.assertIsNotNone(payload['trust_score'])
