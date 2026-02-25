from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import HelpRequest, Skill, Tag


class RequestTagsDiscoveryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='poster', password='pw')
        self.skill = Skill.objects.create(name='Python')

    def test_create_request_parses_and_saves_tags(self):
        self.client.login(username='poster', password='pw')

        response = self.client.post(
            reverse('create_request'),
            {
                'title': 'Tagged task',
                'description': 'Need help with API debugging',
                'skill_needed': self.skill.pk,
                'kp_bounty': 10,
                'tags_input': 'api, debugging, API',
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj = HelpRequest.objects.get(title='Tagged task')
        self.assertQuerySetEqual(
            request_obj.tags.order_by('name').values_list('name', flat=True),
            ['api', 'debugging'],
            transform=lambda value: value,
        )

    def test_request_list_tag_filter_shows_matching_requests(self):
        tag = Tag.objects.create(name='django')

        open_request = HelpRequest.objects.create(
            title='Open django task',
            description='Open task',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=5,
            status='open',
        )
        resolved_request = HelpRequest.objects.create(
            title='Resolved django task',
            description='Resolved task',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=7,
            status='resolved',
        )
        other_request = HelpRequest.objects.create(
            title='Unrelated task',
            description='No tag',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=7,
            status='open',
        )

        open_request.tags.add(tag)
        resolved_request.tags.add(tag)

        response = self.client.get(reverse('request_list'), {'tag': tag.slug})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open django task')
        self.assertContains(response, 'Resolved django task')
        self.assertNotContains(response, 'Unrelated task')

    def test_skill_and_tag_browse_pages_show_request_counts(self):
        django_tag = Tag.objects.create(name='django')
        api_tag = Tag.objects.create(name='api')

        req1 = HelpRequest.objects.create(
            title='First',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=5,
            status='open',
        )
        req2 = HelpRequest.objects.create(
            title='Second',
            description='desc',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=5,
            status='resolved',
        )
        req1.tags.add(django_tag)
        req2.tags.add(django_tag, api_tag)

        skills_response = self.client.get(reverse('skill_browse'))
        tags_response = self.client.get(reverse('tag_browse'))

        self.assertEqual(skills_response.status_code, 200)
        self.assertContains(skills_response, 'Python')
        self.assertContains(skills_response, '2 requests')

        self.assertEqual(tags_response.status_code, 200)
        self.assertContains(tags_response, '#django')
        self.assertContains(tags_response, '2 requests')
        self.assertContains(tags_response, '#api')

    def test_create_request_with_tags_requires_login(self):
        response = self.client.post(
            reverse('create_request'),
            {
                'title': 'No auth',
                'description': 'desc',
                'skill_needed': self.skill.pk,
                'kp_bounty': 5,
                'tags_input': 'auth',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])
