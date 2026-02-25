from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import HelpRequest, Skill, Tag


class RequestManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='poster', password='pw', knowledge_points=80)
        self.other = CustomUser.objects.create_user(username='other', password='pw', knowledge_points=120)
        self.helper = CustomUser.objects.create_user(username='helper', password='pw')
        self.skill = Skill.objects.create(name='Django')

        self.request_obj = HelpRequest.objects.create(
            title='Editable request',
            description='Initial description',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
        )
        self.request_obj.tags.add(Tag.objects.create(name='initial'))

    def test_poster_can_edit_open_request_and_adjust_escrow(self):
        self.client.login(username='poster', password='pw')

        response = self.client.post(
            reverse('edit_request', args=[self.request_obj.pk]),
            {
                'title': 'Edited request',
                'description': 'Updated description',
                'skill_needed': self.skill.pk,
                'kp_bounty': 30,
                'tags_input': 'django, api',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.request_obj.refresh_from_db()
        self.poster.refresh_from_db()

        self.assertEqual(self.request_obj.title, 'Edited request')
        self.assertEqual(self.request_obj.kp_bounty, 30)
        self.assertEqual(self.poster.knowledge_points, 70)
        self.assertQuerySetEqual(
            self.request_obj.tags.order_by('name').values_list('name', flat=True),
            ['api', 'django'],
            transform=lambda value: value,
        )

    def test_non_poster_cannot_edit_or_delete_request(self):
        self.client.login(username='other', password='pw')

        edit_response = self.client.post(
            reverse('edit_request', args=[self.request_obj.pk]),
            {
                'title': 'Malicious edit',
                'description': 'changed',
                'skill_needed': self.skill.pk,
                'kp_bounty': 10,
                'tags_input': 'bad',
            },
        )
        delete_response = self.client.post(reverse('delete_request', args=[self.request_obj.pk]))

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(delete_response.status_code, 302)
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.title, 'Editable request')
        self.assertTrue(HelpRequest.objects.filter(pk=self.request_obj.pk).exists())

    def test_delete_open_request_refunds_kp_and_removes_record(self):
        self.client.login(username='poster', password='pw')

        response = self.client.post(reverse('delete_request', args=[self.request_obj.pk]))

        self.assertEqual(response.status_code, 302)
        self.poster.refresh_from_db()
        self.assertFalse(HelpRequest.objects.filter(pk=self.request_obj.pk).exists())
        self.assertEqual(self.poster.knowledge_points, 100)

    def test_delete_resolved_request_is_blocked(self):
        self.request_obj.status = 'resolved'
        self.request_obj.accepted_by = self.helper
        self.request_obj.save()

        self.client.login(username='poster', password='pw')
        response = self.client.post(reverse('delete_request', args=[self.request_obj.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(HelpRequest.objects.filter(pk=self.request_obj.pk).exists())
