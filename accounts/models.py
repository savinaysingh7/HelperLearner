from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    bio = models.TextField(max_length=500, blank=True)
    knowledge_points = models.IntegerField(default=100)
    last_kp_claim = models.DateTimeField(null=True, blank=True)
    skills = models.ManyToManyField('marketplace.Skill', blank=True, related_name='users')

    def __str__(self):
        return self.username

    class Meta:
        ordering = ['username']
        indexes = [
            models.Index(fields=['knowledge_points']),
            models.Index(fields=['last_kp_claim']),
        ]
