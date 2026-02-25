from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from notifications.models import Notification

from .models import HelpRequest, SavedSearch, Skill, Tag


class SavedSearchFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='search_user', password='pw')
        self.other = CustomUser.objects.create_user(username='other_user', password='pw')
        self.skill = Skill.objects.create(name='Python')
        self.tag = Tag.objects.create(name='django')

    def test_user_can_save_current_filters_from_browse_page(self):
        self.client.login(username='search_user', password='pw')

        response = self.client.post(
            reverse('save_current_search'),
            {'query': 'timeout', 'skill': str(self.skill.pk), 'tag': self.tag.slug},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SavedSearch.objects.filter(user=self.user, query='timeout', skill=self.skill, tag=self.tag).exists())

    def test_save_current_search_rejects_empty_filters(self):
        self.client.login(username='search_user', password='pw')

        response = self.client.post(reverse('save_current_search'), {'query': '', 'skill': '', 'tag': ''})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SavedSearch.objects.filter(user=self.user).count(), 0)

    def test_user_cannot_delete_other_users_saved_search(self):
        saved_search = SavedSearch.objects.create(user=self.other, query='api')
        self.client.login(username='search_user', password='pw')

        response = self.client.post(reverse('delete_saved_search', args=[saved_search.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SavedSearch.objects.filter(pk=saved_search.pk).exists())

    def test_notify_saved_searches_creates_notification_for_new_match(self):
        saved_search = SavedSearch.objects.create(user=self.user, query='timeout')
        saved_search.created_at = timezone.now() - timedelta(minutes=2)
        saved_search.save(update_fields=['created_at'])
        HelpRequest.objects.create(
            title='Timeout issue in production',
            description='Need urgent help',
            user=self.other,
            skill_needed=self.skill,
            kp_bounty=10,
            status='open',
        )

        call_command('notify_saved_searches')

        self.assertEqual(
            Notification.objects.filter(user=self.user, message__contains='match your saved search').count(),
            1,
        )
        saved_search = SavedSearch.objects.get(user=self.user, query='timeout')
        self.assertIsNotNone(saved_search.last_notified_at)

    def test_notify_saved_searches_respects_skill_and_tag_filters(self):
        SavedSearch.objects.create(user=self.user, skill=self.skill, tag=self.tag)
        non_matching = HelpRequest.objects.create(
            title='Python request without tag',
            description='No tag on this one',
            user=self.other,
            skill_needed=self.skill,
            kp_bounty=8,
            status='open',
        )

        call_command('notify_saved_searches')
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

        matching = HelpRequest.objects.create(
            title='Tagged python request',
            description='Has matching skill and tag',
            user=self.other,
            skill_needed=self.skill,
            kp_bounty=12,
            status='open',
        )
        matching.tags.add(self.tag)
        non_matching.tags.add(self.tag)
        non_matching.skill_needed = None
        non_matching.save(update_fields=['skill_needed'])

        call_command('notify_saved_searches')
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
