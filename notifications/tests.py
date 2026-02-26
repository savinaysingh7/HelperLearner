from django.core import mail
from django.test import Client, TestCase, override_settings
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

    def test_notification_page_shows_new_badge_for_items_that_were_unread(self):
        Notification.objects.create(user=self.user, message='Test', link='/', is_read=False)
        self.client.login(username='notify', password='pw')

        response = self.client.get(reverse('notification_list'))

        self.assertContains(response, 'New')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotificationPreferenceSignalTests(TestCase):
    def setUp(self):
        self.poster = CustomUser.objects.create_user(
            username='prefposter',
            password='pw',
            email='prefposter@example.com',
        )
        self.helper = CustomUser.objects.create_user(
            username='prefhelper',
            password='pw',
            email='prefhelper@example.com',
        )
        self.skill = Skill.objects.create(name='Flask')

    def test_claim_transition_email_only_skips_in_app_notification(self):
        self.poster.notification_preference = CustomUser.NotificationPreference.EMAIL
        self.poster.save(update_fields=['notification_preference'])
        request_obj = HelpRequest.objects.create(
            title='Email only claim',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
        )

        mail.outbox.clear()
        request_obj.status = 'in_progress'
        request_obj.accepted_by = self.helper
        request_obj.save()

        self.assertEqual(Notification.objects.filter(user=self.poster).count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['prefposter@example.com'])

    def test_claim_transition_in_app_only_skips_email(self):
        self.poster.notification_preference = CustomUser.NotificationPreference.IN_APP
        self.poster.save(update_fields=['notification_preference'])
        request_obj = HelpRequest.objects.create(
            title='In-app only claim',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
        )

        mail.outbox.clear()
        request_obj.status = 'in_progress'
        request_obj.accepted_by = self.helper
        request_obj.save()

        self.assertEqual(Notification.objects.filter(user=self.poster).count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_cancel_transition_none_blocks_helper_notification_and_email(self):
        self.helper.notification_preference = CustomUser.NotificationPreference.NONE
        self.helper.save(update_fields=['notification_preference'])
        request_obj = HelpRequest.objects.create(
            title='No delivery helper',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='in_progress',
            accepted_by=self.helper,
        )

        mail.outbox.clear()
        request_obj.status = 'canceled'
        request_obj.save()

        self.assertEqual(Notification.objects.filter(user=self.helper).count(), 0)
        self.assertEqual(len(mail.outbox), 0)
