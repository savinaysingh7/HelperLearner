from rest_framework import serializers

from accounts.models import CustomUser

from .models import (
    Comment,
    FreelanceJob,
    HelpRequest,
    JobMilestone,
    Skill,
    WorkspaceIssue,
    WorkspaceIssueComment,
    WorkspaceProject,
    WorkspaceSprint,
)


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


class WorkspaceSprintSerializer(serializers.ModelSerializer):
    """Serializer for sprint metadata linked to workspace issues/projects."""

    class Meta:
        model = WorkspaceSprint
        fields = ['id', 'name', 'status', 'start_date', 'end_date']


class WorkspaceProjectSerializer(serializers.ModelSerializer):
    """Serializer for workspace project boards with issue counters."""

    workspace = serializers.CharField(source='workspace.slug', read_only=True)
    issue_count = serializers.IntegerField(read_only=True)
    open_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = WorkspaceProject
        fields = [
            'id',
            'workspace',
            'name',
            'key',
            'description',
            'is_active',
            'issue_count',
            'open_count',
            'created_at',
            'updated_at',
        ]


class WorkspaceIssueSerializer(serializers.ModelSerializer):
    """Serializer for workspace issues in Jira-style board APIs."""

    issue_key = serializers.CharField(read_only=True)
    project = serializers.CharField(source='project.key', read_only=True)
    workspace = serializers.CharField(source='project.workspace.slug', read_only=True)
    reporter = serializers.CharField(source='reporter.username', read_only=True)
    assignee = serializers.CharField(source='assignee.username', read_only=True)
    sprint = WorkspaceSprintSerializer(read_only=True)

    class Meta:
        model = WorkspaceIssue
        fields = [
            'id',
            'issue_key',
            'project',
            'workspace',
            'title',
            'description',
            'status',
            'priority',
            'reporter',
            'assignee',
            'estimate_points',
            'sprint',
            'due_date',
            'resolved_at',
            'created_at',
            'updated_at',
        ]


class WorkspaceIssueCommentSerializer(serializers.ModelSerializer):
    """Serializer for timeline comments on workspace issues."""

    author = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = WorkspaceIssueComment
        fields = ['id', 'author', 'content', 'created_at', 'updated_at']
