from rest_framework import serializers
from .models import HelpRequest, Skill
from accounts.models import CustomUser

class HelpRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for the HelpRequest model.
    """
    user = serializers.CharField(source='user.username', read_only=True)
    skill_needed = serializers.CharField(source='skill_needed.name', read_only=True)

    class Meta:
        model = HelpRequest
        fields = ['id', 'title', 'description', 'user', 'skill_needed', 'kp_bounty', 'status', 'created_at']
