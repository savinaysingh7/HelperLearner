from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    bio = models.TextField(max_length=500, blank=True)
    knowledge_points = models.IntegerField(default=100)

    def __str__(self):
        return self.username
