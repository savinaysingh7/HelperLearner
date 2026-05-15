"""Tests for new features: GDPR export, helper matching, content moderation, portfolio, sprint burndown."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from marketplace.matching import get_recommended_helpers
from marketplace.moderation import moderate_text
from marketplace.models import (
    Attachment,
    FreelanceJob,
    HelpRequest,
    PortfolioItem,
    Rating,
    Skill,
    Workspace,
    WorkspaceMembership,
)


class HelperMatchingTests(TestCase):
    def setUp(self):
        self.skill = Skill.objects.create(name='Python')
        self.poster = CustomUser.objects.create_user(username='poster', password='pw', email='p@t.com')
        self.helper1 = CustomUser.objects.create_user(username='helper1', password='pw', email='h1@t.com')
        self.helper2 = CustomUser.objects.create_user(username='helper2', password='pw', email='h2@t.com')
        self.helper1.skills.add(self.skill)
        self.helper1.trust_score = 80
        self.helper1.save()

    def test_matching_returns_scored_helpers(self):
        hr = HelpRequest.objects.create(
            title='Need Python help', description='Test', user=self.poster,
            skill_needed=self.skill, kp_bounty=10,
        )
        results = get_recommended_helpers(hr, limit=5)
        self.assertTrue(len(results) > 0)
        usernames = [u.username for u, _ in results]
        self.assertIn('helper1', usernames)

    def test_matching_excludes_poster(self):
        hr = HelpRequest.objects.create(
            title='Self help', description='Test', user=self.poster,
            skill_needed=self.skill, kp_bounty=10,
        )
        results = get_recommended_helpers(hr, limit=10)
        usernames = [u.username for u, _ in results]
        self.assertNotIn('poster', usernames)

    def test_matching_empty_for_none(self):
        results = get_recommended_helpers(None)
        self.assertEqual(results, [])

    def test_skill_match_gives_higher_score(self):
        hr = HelpRequest.objects.create(
            title='Python help', description='Test', user=self.poster,
            skill_needed=self.skill, kp_bounty=10,
        )
        results = get_recommended_helpers(hr, limit=10)
        scores = {u.username: s for u, s in results}
        # helper1 has skill match, helper2 doesn't
        if 'helper1' in scores and 'helper2' in scores:
            self.assertGreater(scores['helper1'], scores['helper2'])


class ContentModerationTests(TestCase):
    def test_safe_content(self):
        result = moderate_text('I need help with Django models.')
        self.assertEqual(result['status'], 'safe')

    def test_blocked_content(self):
        result = moderate_text('How to exploit SQL injection')
        self.assertEqual(result['status'], 'blocked')

    def test_flagged_content(self):
        result = moderate_text('Contact me on whatsapp for the deal')
        self.assertEqual(result['status'], 'flagged')

    def test_empty_text(self):
        result = moderate_text('')
        self.assertEqual(result['status'], 'safe')

    def test_none_text(self):
        result = moderate_text(None)
        self.assertEqual(result['status'], 'safe')


class PublicPortfolioTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='devuser', password='pw', email='d@t.com')
        self.skill = Skill.objects.create(name='React')
        PortfolioItem.objects.create(
            user=self.user, title='My Project', summary='A cool project',
            primary_skill=self.skill,
        )

    def test_public_portfolio_accessible(self):
        response = self.client.get(f'/u/{self.user.username}/portfolio/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Project')
        self.assertContains(response, 'devuser')

    def test_public_portfolio_404_for_nonexistent_user(self):
        response = self.client.get('/u/nonexistentuser/portfolio/')
        self.assertEqual(response.status_code, 404)


class GDPRExportTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = CustomUser.objects.create_user(username='exportuser', password='pw', email='e@t.com')

    def test_export_requires_login(self):
        response = self.client.get('/accounts/export/')
        self.assertEqual(response.status_code, 302)

    def test_export_returns_zip(self):
        self.client.login(username='exportuser', password='pw')
        response = self.client.get('/accounts/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

    def test_export_rate_limited(self):
        self.client.login(username='exportuser', password='pw')
        # First export
        response1 = self.client.get('/accounts/export/')
        self.assertEqual(response1.status_code, 200)
        # Second export should be rate limited
        response2 = self.client.get('/accounts/export/')
        self.assertEqual(response2.status_code, 429)


class AttachmentDownloadCountTests(TestCase):
    def test_download_count_default(self):
        user = CustomUser.objects.create_user(username='attachuser', password='pw')
        hr = HelpRequest.objects.create(
            title='Test', description='Test', user=user, kp_bounty=5,
        )
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(HelpRequest)
        attachment = Attachment.objects.create(
            content_type=ct, object_id=hr.pk,
            uploaded_by=user, file='test.txt',
        )
        self.assertEqual(attachment.download_count, 0)
        attachment.download_count += 1
        attachment.save()
        attachment.refresh_from_db()
        self.assertEqual(attachment.download_count, 1)


class NotificationPreferenceTests(TestCase):
    def test_default_notification_prefs(self):
        user = CustomUser.objects.create_user(username='prefuser', password='pw')
        self.assertTrue(user.notify_requests)
        self.assertTrue(user.notify_jobs)
        self.assertTrue(user.notify_chat)
        self.assertTrue(user.notify_kp)

    def test_notification_prefs_can_be_disabled(self):
        user = CustomUser.objects.create_user(username='prefuser2', password='pw')
        user.notify_chat = False
        user.notify_kp = False
        user.save()
        user.refresh_from_db()
        self.assertFalse(user.notify_chat)
        self.assertFalse(user.notify_kp)
        self.assertTrue(user.notify_requests)
        self.assertTrue(user.notify_jobs)
