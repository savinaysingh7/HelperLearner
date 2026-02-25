from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import Comment, HelpRequest, Skill


class ActivityFeedTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='alice', password='pw')
        self.interacted_user = CustomUser.objects.create_user(username='bob', password='pw')
        self.helper = CustomUser.objects.create_user(username='charlie', password='pw')
        self.stranger = CustomUser.objects.create_user(username='dana', password='pw')

        self.python = Skill.objects.create(name='Python')
        self.java = Skill.objects.create(name='Java')
        self.user.skills.add(self.python)

        HelpRequest.objects.create(
            title='Old interaction request',
            description='History',
            user=self.interacted_user,
            skill_needed=self.python,
            kp_bounty=5,
            status='in_progress',
            accepted_by=self.user,
        )
        HelpRequest.objects.create(
            title='Alice asked Charlie',
            description='Completed interaction',
            user=self.user,
            skill_needed=self.java,
            kp_bounty=6,
            status='resolved',
            accepted_by=self.helper,
        )

        self.interacted_post = HelpRequest.objects.create(
            title='Interacted user posted this',
            description='Should appear in feed',
            user=self.interacted_user,
            skill_needed=self.java,
            kp_bounty=7,
            status='open',
        )
        self.skill_match = HelpRequest.objects.create(
            title='Python request match',
            description='Matches user skill',
            user=self.stranger,
            skill_needed=self.python,
            kp_bounty=8,
            status='open',
        )
        commented_request = HelpRequest.objects.create(
            title='Request I commented on',
            description='Track resolution',
            user=self.stranger,
            skill_needed=self.java,
            kp_bounty=9,
            status='in_progress',
            accepted_by=self.helper,
        )
        Comment.objects.create(request=commented_request, user=self.user, content='Following this thread')
        commented_request.status = 'resolved'
        commented_request.save()

        self.irrelevant = HelpRequest.objects.create(
            title='Irrelevant Java request',
            description='Should not appear',
            user=self.stranger,
            skill_needed=self.java,
            kp_bounty=4,
            status='open',
        )

    def test_feed_shows_relevant_activity_items(self):
        self.client.login(username='alice', password='pw')

        response = self.client.get(reverse('activity_feed'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.interacted_post.title)
        self.assertContains(response, self.skill_match.title)
        self.assertContains(response, 'Request I commented on')

    def test_feed_excludes_irrelevant_items(self):
        self.client.login(username='alice', password='pw')

        response = self.client.get(reverse('activity_feed'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.irrelevant.title)

    def test_feed_requires_authentication(self):
        response = self.client.get(reverse('activity_feed'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])
