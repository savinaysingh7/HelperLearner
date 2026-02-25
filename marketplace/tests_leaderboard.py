from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import HelpRequest, Rating, Skill


class LeaderboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.skill = Skill.objects.create(name='Python')

        self.poster = CustomUser.objects.create_user(username='poster', password='pw', knowledge_points=50)
        self.kp_leader = CustomUser.objects.create_user(username='kp_leader', password='pw', knowledge_points=400)
        self.help_leader = CustomUser.objects.create_user(username='help_leader', password='pw', knowledge_points=120)
        self.rating_leader = CustomUser.objects.create_user(username='rating_leader', password='pw', knowledge_points=130)

        self.help_leader.skills.add(self.skill)
        self.rating_leader.skills.add(self.skill)

        resolved_1 = HelpRequest.objects.create(
            title='Solved A',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='resolved',
            accepted_by=self.help_leader,
        )
        resolved_2 = HelpRequest.objects.create(
            title='Solved B',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=12,
            status='resolved',
            accepted_by=self.help_leader,
        )
        resolved_3 = HelpRequest.objects.create(
            title='Solved C',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=8,
            status='resolved',
            accepted_by=self.rating_leader,
        )

        Rating.objects.create(request=resolved_1, given_by=self.poster, given_to=self.help_leader, score=4)
        Rating.objects.create(request=resolved_2, given_by=self.poster, given_to=self.help_leader, score=4)
        Rating.objects.create(request=resolved_3, given_by=self.poster, given_to=self.rating_leader, score=5)

    def test_leaderboard_is_public_and_kp_tab_default(self):
        response = self.client.get(reverse('leaderboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tab'], 'kp')
        self.assertEqual(response.context['active_leaders'][0].username, 'kp_leader')

    def test_helped_tab_orders_by_resolved_help_count(self):
        response = self.client.get(reverse('leaderboard'), {'tab': 'helped'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tab'], 'helped')
        self.assertEqual(response.context['active_leaders'][0].username, 'help_leader')

    def test_rating_tab_and_hall_of_fame_show_highest_rated_helper(self):
        response = self.client.get(reverse('leaderboard'), {'tab': 'rating'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tab'], 'rating')
        self.assertEqual(response.context['active_leaders'][0].username, 'rating_leader')
        self.assertEqual(response.context['hall_of_fame'].username, 'rating_leader')
