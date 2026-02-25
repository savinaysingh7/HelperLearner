from django.test import Client, TestCase
from django.urls import reverse

from marketplace.models import HelpRequest, Rating, Skill

from .models import CustomUser


class DashboardFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='dash', password='pw')
        self.other = CustomUser.objects.create_user(username='other', password='pw')
        self.skill = Skill.objects.create(name='APIs')

    def test_dashboard_shows_expected_aggregated_metrics(self):
        helped_request = HelpRequest.objects.create(
            title='Helped item',
            description='Resolved with my help',
            user=self.other,
            skill_needed=self.skill,
            kp_bounty=20,
            status='resolved',
            accepted_by=self.user,
        )
        HelpRequest.objects.create(
            title='Posted resolved',
            description='Resolved post',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=10,
            status='resolved',
            accepted_by=self.other,
        )
        HelpRequest.objects.create(
            title='Posted canceled',
            description='Canceled post',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=5,
            status='canceled',
        )
        Rating.objects.create(
            request=helped_request,
            given_by=self.other,
            given_to=self.user,
            score=4,
        )

        self.client.login(username='dash', password='pw')
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_kp_earned'], 20)
        self.assertEqual(response.context['total_kp_spent'], 15)
        self.assertEqual(response.context['requests_posted_count'], 2)
        self.assertEqual(response.context['requests_helped_count'], 1)
        self.assertEqual(response.context['success_rate'], 50.0)
        self.assertEqual(response.context['average_rating_received'], 4.0)

    def test_dashboard_handles_no_activity_edge_case(self):
        self.client.login(username='dash', password='pw')

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_kp_earned'], 0)
        self.assertEqual(response.context['total_kp_spent'], 0)
        self.assertEqual(response.context['success_rate'], 0)
        self.assertEqual(len(response.context['monthly_activity']), 6)
        self.assertTrue(all(item['total_count'] == 0 for item in response.context['monthly_activity']))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])
