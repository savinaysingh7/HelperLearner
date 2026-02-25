from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from marketplace.models import HelpRequest, Skill

from .models import Notification


class NotificationSignalTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='poster', password='pw')
        self.helper = CustomUser.objects.create_user(username='helper', password='pw')
        self.skill = Skill.objects.create(name='Django')
        self.request_obj = HelpRequest.objects.create(
            title='Need help',
            description='Please help',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=12,
        )

    def test_in_progress_transition_creates_notification_for_poster(self):
        self.request_obj.status = 'in_progress'
        self.request_obj.accepted_by = self.helper
        self.request_obj.save()

        notification = Notification.objects.get(user=self.poster)
        self.assertIn('Someone accepted your request', notification.message)
        self.assertEqual(notification.link, reverse('request_detail', args=[self.request_obj.pk]))

    def test_canceled_without_helper_does_not_create_helper_notification(self):
        self.request_obj.status = 'canceled'
        self.request_obj.save()

        self.assertEqual(Notification.objects.count(), 0)

    def test_resolved_transition_notifies_helper_with_kp_message(self):
        self.request_obj.status = 'in_progress'
        self.request_obj.accepted_by = self.helper
        self.request_obj.save()

        self.request_obj.status = 'resolved'
        self.request_obj.save()

        helper_notifications = Notification.objects.filter(user=self.helper)
        self.assertEqual(helper_notifications.count(), 1)
        self.assertIn('Your help was marked resolved!', helper_notifications.first().message)


class NotificationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='notify', password='pw')

    def test_notification_page_requires_login(self):
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    def test_notification_page_marks_unread_items_read(self):
        Notification.objects.create(user=self.user, message='Test', link='/')
        self.client.login(username='notify', password='pw')

        response = self.client.get(reverse('notification_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.notifications.filter(is_read=False).count(), 0)
