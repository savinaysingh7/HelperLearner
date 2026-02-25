from django.test import Client, TestCase
from django.urls import reverse

from marketplace.models import HelpRequest, Skill

from .models import CustomUser


class UserSkillsFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='skills_user', password='pw')
        self.other = CustomUser.objects.create_user(username='helper_user', password='pw')
        self.python = Skill.objects.create(name='Python')
        self.django = Skill.objects.create(name='Django')

    def test_user_can_add_and_remove_skills_from_edit_profile(self):
        self.client.login(username='skills_user', password='pw')

        response = self.client.post(reverse('edit_profile'), {
            'email': 'skills@example.com',
            'bio': 'Updated',
            'skills': [self.python.pk, self.django.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertQuerySetEqual(
            self.user.skills.order_by('name').values_list('name', flat=True),
            ['Django', 'Python'],
            transform=lambda x: x,
        )

    def test_request_list_shows_registered_users_with_required_skill(self):
        self.user.skills.add(self.python)
        self.other.skills.add(self.python)
        HelpRequest.objects.create(
            title='Need Python help',
            description='Skill count check',
            user=self.user,
            skill_needed=self.python,
            kp_bounty=5,
        )

        response = self.client.get(reverse('request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2 registered users with this skill')

    def test_edit_profile_skills_update_requires_login(self):
        response = self.client.post(reverse('edit_profile'), {
            'email': 'blocked@example.com',
            'bio': 'Blocked update',
            'skills': [self.python.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.skills.count(), 0)

    def test_public_profile_displays_skill_badges(self):
        self.user.skills.add(self.python, self.django)

        response = self.client.get(reverse('public_profile', args=[self.user.username]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Python')
        self.assertContains(response, 'Django')
