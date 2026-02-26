from rest_framework import serializers

from accounts.models import CustomUser

from .models import Comment, FreelanceJob, HelpRequest, JobMilestone, Skill


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


class JobMilestoneSerializer(serializers.ModelSerializer):
    """Serializer for milestone details in paid job responses."""

    class Meta:
        model = JobMilestone
        fields = ['id', 'title', 'amount_inr', 'sequence', 'status', 'submitted_at', 'released_at']


class FreelanceJobSerializer(serializers.ModelSerializer):
    """Serializer for paid freelance jobs with milestone visibility."""

    client = serializers.CharField(source='client.username', read_only=True)
    freelancer = serializers.CharField(source='freelancer.username', read_only=True)
    skill_needed = serializers.CharField(source='skill_needed.name', read_only=True)
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    milestones = JobMilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = FreelanceJob
        fields = [
            'id',
            'title',
            'description',
            'client',
            'freelancer',
            'skill_needed',
            'payment_type',
            'budget_inr',
            'escrow_inr',
            'status',
            'deadline',
            'response_sla_hours',
            'tags',
            'milestones',
            'created_at',
            'updated_at',
        ]
