from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import HelpRequest, Rating, Skill


class RatingFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='poster', password='pw')
        self.helper = CustomUser.objects.create_user(username='helper', password='pw')
        self.other = CustomUser.objects.create_user(username='other', password='pw')
        self.skill = Skill.objects.create(name='Python')

        self.resolved_request = HelpRequest.objects.create(
            title='Resolved Task',
            description='Done',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='resolved',
            accepted_by=self.helper,
        )
        self.open_request = HelpRequest.objects.create(
            title='Open Task',
            description='Not done',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=8,
            status='open',
            accepted_by=self.helper,
        )

    def test_poster_can_rate_resolved_helper_once(self):
        self.client.login(username='poster', password='pw')

        response = self.client.post(reverse('rate_request', args=[self.resolved_request.pk]), {'score': 5})

        self.assertEqual(response.status_code, 302)
        rating = Rating.objects.get(request=self.resolved_request)
        self.assertEqual(rating.given_by, self.poster)
        self.assertEqual(rating.given_to, self.helper)
        self.assertEqual(rating.score, 5)

    def test_cannot_rate_unresolved_request(self):
        self.client.login(username='poster', password='pw')

        response = self.client.post(reverse('rate_request', args=[self.open_request.pk]), {'score': 4})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Rating.objects.filter(request=self.open_request).exists())

    def test_non_poster_cannot_rate_request(self):
        self.client.login(username='other', password='pw')

        response = self.client.post(reverse('rate_request', args=[self.resolved_request.pk]), {'score': 3})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Rating.objects.filter(request=self.resolved_request).exists())

    def test_duplicate_rating_is_blocked(self):
        Rating.objects.create(
            request=self.resolved_request,
            given_by=self.poster,
            given_to=self.helper,
            score=4,
        )
        self.client.login(username='poster', password='pw')

        response = self.client.post(reverse('rate_request', args=[self.resolved_request.pk]), {'score': 2})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Rating.objects.filter(request=self.resolved_request).count(), 1)
        self.assertEqual(Rating.objects.get(request=self.resolved_request).score, 4)
