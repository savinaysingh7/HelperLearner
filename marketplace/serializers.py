from rest_framework import serializers

from accounts.models import CustomUser

from .models import Comment, HelpRequest, Skill


class HelpRequestSerializer(serializers.ModelSerializer):
    """Serializer for request discovery endpoints."""

    user = serializers.CharField(source='user.username', read_only=True)
    skill_needed = serializers.CharField(source='skill_needed.name', read_only=True)
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')

    class Meta:
        model = HelpRequest
        fields = [
            'id',
            'title',
            'description',
            'user',
            'skill_needed',
            'tags',
            'kp_bounty',
            'status',
            'created_at',
            'expires_at',
        ]


class PublicUserSerializer(serializers.ModelSerializer):
    """Serializer for API user listing with rating, trust, KP, and skills."""

    avg_rating = serializers.FloatField(read_only=True)
    trust_score = serializers.FloatField(read_only=True)
    skills = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'avg_rating', 'trust_score', 'knowledge_points', 'skills']


class SkillSerializer(serializers.ModelSerializer):
    """Serializer for skills with request-count annotations."""

    request_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Skill
        fields = ['id', 'name', 'request_count']


class PublicCommentSerializer(serializers.ModelSerializer):
    """Serializer for public request comments only."""

    user = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'user', 'content', 'created_at']
