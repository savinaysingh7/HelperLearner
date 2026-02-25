from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import CustomUser
from .models import HelpRequest, Skill

class MarketplaceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = CustomUser.objects.create_user(username='user1', password='password123', knowledge_points=100)
        self.user2 = CustomUser.objects.create_user(username='user2', password='password123', knowledge_points=50)
        self.skill = Skill.objects.create(name='Python')

    def test_create_request_success(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('create_request'), {
            'title': 'Test Request',
            'description': 'Test Description',
            'skill_needed': self.skill.id,
            'kp_bounty': 50
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HelpRequest.objects.count(), 1)
        req = HelpRequest.objects.first()
        self.assertEqual(req.user, self.user1)

    def test_create_request_insufficient_kp(self):
        self.client.login(username='user2', password='password123')
        response = self.client.post(reverse('create_request'), {
            'title': 'Test Request',
            'description': 'Test Description',
            'skill_needed': self.skill.id,
            'kp_bounty': 100
        })
        # Should not redirect, should stay on page with error
        self.assertEqual(response.status_code, 200)
        self.assertEqual(HelpRequest.objects.count(), 0)

    def test_claim_request(self):
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20
        )
        self.client.login(username='user2', password='password123')
        response = self.client.post(reverse('claim_request', args=[req.id]))
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'in_progress')
        self.assertEqual(req.accepted_by, self.user2)

    def test_resolve_request_kp_transfer(self):
        self.user1.knowledge_points -= 20
        self.user1.save()
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20,
            status='in_progress',
            accepted_by=self.user2
        )
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('resolve_request', args=[req.id]))
        self.assertEqual(response.status_code, 302)
        
        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        req.refresh_from_db()
        
        self.assertEqual(self.user1.knowledge_points, 80)
        self.assertEqual(self.user2.knowledge_points, 70)
        self.assertEqual(req.status, 'resolved')

    def test_cancel_request_kp_refund(self):
        self.user1.knowledge_points = 80  # simulating 20 already in escrow
        self.user1.save()
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open'
        )
        self.client.login(username='user1', password='password123')
        response = self.client.post(reverse('cancel_request', args=[req.id]))
        self.assertEqual(response.status_code, 302)

        self.user1.refresh_from_db()
        req.refresh_from_db()

        self.assertEqual(self.user1.knowledge_points, 100)  # refunded
        self.assertEqual(req.status, 'canceled')

    def test_cannot_claim_own_request(self):
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20
        )
        self.client.login(username='user1', password='password123')
        self.client.post(reverse('claim_request', args=[req.id]))

        req.refresh_from_db()
        self.assertEqual(req.status, 'open')  # should not have changed

    def test_create_request_redirects_if_not_logged_in(self):
        response = self.client.get(reverse('create_request'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    def test_private_comment_visibility(self):
        # user1 is requester, user2 is helper
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20,
            status='in_progress',
            accepted_by=self.user2
        )
        
        from .models import Comment
        # Create a private comment from requester
        Comment.objects.create(request=req, user=self.user1, content='Private info', is_private=True)
        # Create a public comment
        Comment.objects.create(request=req, user=self.user1, content='Public info', is_private=False)
        
        # 1. Requester should see both
        self.client.login(username='user1', password='password123')
        response = self.client.get(reverse('request_detail', args=[req.id]))
        self.assertContains(response, 'Private info')
        self.assertContains(response, 'Public info')
        self.client.logout()
        
        # 2. Helper should see both
        self.client.login(username='user2', password='password123')
        response = self.client.get(reverse('request_detail', args=[req.id]))
        self.assertContains(response, 'Private info')
        self.assertContains(response, 'Public info')
        self.client.logout()
        
        # 3. Third party should only see public
        user3 = CustomUser.objects.create_user(username='user3', password='password123')
        self.client.login(username='user3', password='password123')
        response = self.client.get(reverse('request_detail', args=[req.id]))
        self.assertNotContains(response, 'Private info')
        self.assertContains(response, 'Public info')

    def test_third_party_cannot_post_private_comment(self):
        req = HelpRequest.objects.create(
            title='Help me',
            description='I need help',
            user=self.user1,
            skill_needed=self.skill,
            kp_bounty=20
        )
        user3 = CustomUser.objects.create_user(username='user3', password='password123')
        self.client.login(username='user3', password='password123')
        
        # Attempt to post a private comment
        self.client.post(reverse('request_detail', args=[req.id]), {
            'content': 'Attempted private comment',
            'is_private': True
        })
        
        from .models import Comment
        comment = Comment.objects.get(content='Attempted private comment')
        self.assertFalse(comment.is_private)
