from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from accounts.admin import CustomUserAdmin
from accounts.models import CustomUser
from notifications.admin import NotificationAdmin
from notifications.models import Notification

from .admin import HelpRequestAdmin
from .models import HelpRequest, Rating, Skill


class CustomAdminFeatureTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.superuser = CustomUser.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='pw123456!',
        )
        self.poster = CustomUser.objects.create_user(username='poster', password='pw')
        self.helper = CustomUser.objects.create_user(username='helper', password='pw')
        self.skill = Skill.objects.create(name='Python')

    def _admin_request(self):
        request = self.factory.post('/admin/')
        request.user = self.superuser
        return request

    def test_help_request_admin_mark_as_expired_refunds_open_request(self):
        self.poster.knowledge_points = 80
        self.poster.save(update_fields=['knowledge_points'])
        help_request = HelpRequest.objects.create(
            title='Admin expire me',
            description='Pending',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
        )

        admin_obj = HelpRequestAdmin(HelpRequest, self.site)
        admin_obj.message_user = lambda *args, **kwargs: None
        admin_obj.mark_as_expired(self._admin_request(), HelpRequest.objects.filter(pk=help_request.pk))

        help_request.refresh_from_db()
        self.poster.refresh_from_db()
        self.assertEqual(help_request.status, 'canceled')
        self.assertEqual(self.poster.knowledge_points, 100)

    def test_help_request_admin_mark_as_expired_skips_non_open_requests(self):
        self.poster.knowledge_points = 80
        self.poster.save(update_fields=['knowledge_points'])
        help_request = HelpRequest.objects.create(
            title='In progress request',
            description='Do not expire',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='in_progress',
            accepted_by=self.helper,
        )

        admin_obj = HelpRequestAdmin(HelpRequest, self.site)
        admin_obj.message_user = lambda *args, **kwargs: None
        admin_obj.mark_as_expired(self._admin_request(), HelpRequest.objects.filter(pk=help_request.pk))

        help_request.refresh_from_db()
        self.poster.refresh_from_db()
        self.assertEqual(help_request.status, 'in_progress')
        self.assertEqual(self.poster.knowledge_points, 80)

    def test_notification_admin_mark_all_read_action(self):
        unread_one = Notification.objects.create(user=self.poster, message='A', link='/')
        unread_two = Notification.objects.create(user=self.poster, message='B', link='/')
        Notification.objects.create(user=self.poster, message='C', link='/', is_read=True)

        admin_obj = NotificationAdmin(Notification, self.site)
        admin_obj.message_user = lambda *args, **kwargs: None
        admin_obj.mark_all_read(self._admin_request(), Notification.objects.filter(pk__in=[unread_one.pk, unread_two.pk]))

        self.assertEqual(Notification.objects.filter(user=self.poster, is_read=False).count(), 0)

    def test_custom_user_admin_displays_avg_rating(self):
        resolved_request = HelpRequest.objects.create(
            title='Resolved item',
            description='Done',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='resolved',
            accepted_by=self.helper,
        )
        Rating.objects.create(
            request=resolved_request,
            given_by=self.poster,
            given_to=self.helper,
            score=4,
        )

        admin_obj = CustomUserAdmin(CustomUser, self.site)
        helper_obj = admin_obj.get_queryset(self._admin_request()).get(pk=self.helper.pk)
        self.assertEqual(admin_obj.avg_rating_display(helper_obj), 4.0)
