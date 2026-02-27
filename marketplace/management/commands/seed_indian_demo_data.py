from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from notifications.models import Notification

from marketplace.models import (
    Attachment,
    ChatMessage,
    ChatThread,
    ChatThreadParticipant,
    Comment,
    Experiment,
    ExperimentAssignment,
    ExperimentVariant,
    FraudAlert,
    FreelanceJob,
    FreelanceJobProposal,
    FreelanceJobProposalMilestone,
    HelpRequest,
    HelpRequestProposal,
    IntegrationApiKey,
    JobDispute,
    JobMilestone,
    KPTransfer,
    MilestoneDeliverable,
    ModerationFlag,
    PayoutRequest,
    PortfolioItem,
    Rating,
    SavedSearch,
    Skill,
    Tag,
    TrustSignal,
    WalletLedger,
    WebhookDelivery,
    WebhookEndpoint,
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceIssueComment,
    WorkspaceMembership,
    WorkspaceProject,
    WorkspaceSprint,
    WorkspaceWalletEntry,
)


class Command(BaseCommand):
    help = (
        "Replace existing seeded/demo data with realistic Indian demo data that exercises "
        "KP requests, proposals, ratings, notifications, paid jobs, milestones, disputes, "
        "wallet ledger, payouts, saved searches, workspace Jira boards, chat threads, "
        "integrations, moderation, fraud alerts, transfers, and experiments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="IndiaSeed@2026",
            help="Password applied to all seeded demo users.",
        )
        parser.add_argument(
            "--drop-superusers",
            action="store_true",
            help="Also delete superusers before reseeding.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        drop_superusers = options["drop_superusers"]
        now = timezone.now()

        with transaction.atomic():
            self._clear_existing_data(drop_superusers=drop_superusers)
            seeded = self._seed_dataset(now=now, password=password)

        self._write_seed_credentials_file(
            users=seeded["users"],
            password=password,
            generated_at=now,
            summary=seeded["summary"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seed complete: "
                f"{seeded['summary']['users']} users, "
                f"{seeded['summary']['help_requests']} help requests, "
                f"{seeded['summary']['jobs']} paid jobs, "
                f"{seeded['summary']['notifications']} notifications, "
                f"{seeded['summary']['workspaces']} workspaces, "
                f"{seeded['summary']['issues']} workspace issues."
            )
        )
        self.stdout.write(self.style.SUCCESS("Updated SEEDED_CREDENTIALS.md with new demo logins."))

    def _clear_existing_data(self, drop_superusers: bool):
        Notification.objects.all().delete()

        ExperimentAssignment.objects.all().delete()
        ExperimentVariant.objects.all().delete()
        Experiment.objects.all().delete()

        WebhookDelivery.objects.all().delete()
        WebhookEndpoint.objects.all().delete()
        IntegrationApiKey.objects.all().delete()
        PortfolioItem.objects.all().delete()

        ChatMessage.objects.all().delete()
        ChatThreadParticipant.objects.all().delete()
        ChatThread.objects.all().delete()

        WorkspaceIssueComment.objects.all().delete()
        WorkspaceIssueActivity.objects.all().delete()
        WorkspaceIssue.objects.all().delete()
        WorkspaceSprint.objects.all().delete()
        WorkspaceProject.objects.all().delete()
        WorkspaceWalletEntry.objects.all().delete()
        WorkspaceMembership.objects.all().delete()
        Workspace.objects.all().delete()

        KPTransfer.objects.all().delete()
        FraudAlert.objects.all().delete()
        ModerationFlag.objects.all().delete()
        Attachment.objects.all().delete()
        MilestoneDeliverable.objects.all().delete()

        Rating.objects.all().delete()
        Comment.objects.all().delete()
        HelpRequestProposal.objects.all().delete()
        SavedSearch.objects.all().delete()
        HelpRequest.objects.all().delete()

        FreelanceJobProposalMilestone.objects.all().delete()
        FreelanceJobProposal.objects.all().delete()
        JobDispute.objects.all().delete()
        JobMilestone.objects.all().delete()
        TrustSignal.objects.all().delete()
        PayoutRequest.objects.all().delete()
        WalletLedger.objects.all().delete()
        FreelanceJob.objects.all().delete()

        Tag.objects.all().delete()
        Skill.objects.all().delete()

        if drop_superusers:
            CustomUser.objects.all().delete()
            self.stdout.write(self.style.WARNING("Deleted all users including superusers."))
        else:
            deleted, _ = CustomUser.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.WARNING(f"Deleted non-superuser accounts (rows removed: {deleted})."))

    def _seed_dataset(self, now, password):
        skills = self._create_skills()
        tags = self._create_tags()
        users = self._create_users(skills=skills, password=password, now=now)

        requests = self._create_help_requests(users=users, skills=skills, tags=tags, now=now)
        request_proposals = self._create_help_request_proposals(requests=requests, users=users, now=now)
        self._create_request_comments(requests=requests, users=users, now=now)
        self._create_ratings(requests=requests, users=users, now=now)
        self._create_saved_searches(users=users, skills=skills, tags=tags, now=now)

        jobs, milestones = self._create_jobs_and_milestones(users=users, skills=skills, tags=tags, now=now)
        self._create_job_proposals(jobs=jobs, users=users, now=now)
        disputes = self._create_disputes(jobs=jobs, users=users, now=now)
        self._create_wallet_and_payout_data(jobs=jobs, milestones=milestones, users=users, now=now)
        self._create_trust_signals(jobs=jobs, users=users, now=now)
        notification_count = self._create_notifications(
            users=users,
            requests=requests,
            jobs=jobs,
            request_proposals=request_proposals,
            disputes=disputes,
            now=now,
        )
        workspaces, projects, issues = self._create_workspaces_and_projects(
            users=users,
            skills=skills,
            now=now,
        )
        sprints = self._create_sprints(workspaces=workspaces, projects=projects, users=users, now=now)
        self._attach_issues_to_sprints(issues=issues, sprints=sprints, now=now)
        self._create_issue_comments_and_activity(issues=issues, users=users, now=now)
        self._create_chat_data(
            users=users,
            requests=requests,
            jobs=jobs,
            workspaces=workspaces,
            now=now,
        )
        self._create_portfolio_data(users=users, skills=skills, now=now)
        self._create_integrations_data(users=users, now=now)
        self._create_moderation_and_fraud_data(
            users=users,
            requests=requests,
            jobs=jobs,
            disputes=disputes,
            now=now,
        )
        self._create_kp_transfer_data(users=users, now=now)
        self._create_attachment_data(
            users=users,
            requests=requests,
            jobs=jobs,
            issues=issues,
            now=now,
        )
        self._create_deliverables_data(milestones=milestones, users=users, now=now)
        self._create_experiment_data(users=users, now=now)
        self._expand_saved_search_activity(users=users, skills=skills, tags=tags, now=now)

        summary = {
            "users": len(users),
            "help_requests": len(requests),
            "jobs": len(jobs),
            "notifications": Notification.objects.count(),
            "workspaces": len(workspaces),
            "projects": len(projects),
            "issues": len(issues),
            "chat_messages": ChatMessage.objects.count(),
            "attachments": Attachment.objects.count(),
        }
        return {"users": users, "summary": summary}

    def _create_skills(self):
        skill_names = [
            "Python",
            "Django",
            "Django REST",
            "React",
            "Next.js",
            "Node.js",
            "PostgreSQL",
            "DevOps",
            "AWS",
            "Data Engineering",
            "Flutter",
            "Android",
            "UI/UX",
            "Machine Learning",
            "Prompt Engineering",
            "Testing",
            "Redis",
            "Docker",
            "System Design",
            "Cybersecurity",
            "Search",
        ]
        return {name: Skill.objects.create(name=name) for name in skill_names}

    def _create_tags(self):
        tag_names = [
            "debugging",
            "production",
            "deployment",
            "api",
            "payments",
            "gst",
            "upi",
            "authentication",
            "performance",
            "frontend",
            "database",
            "testing",
            "devops",
            "docker",
            "redis",
            "ai",
            "mobile",
            "flutter",
            "react",
            "invoices",
            "analytics",
            "search",
            "backend",
            "security",
            "validation",
            "ci",
            "data",
            "python",
            "django",
        ]
        return {name: Tag.objects.create(name=name) for name in tag_names}

    def _create_users(self, skills, password, now):
        user_specs = [
            {
                "username": "ananya_sharma",
                "first_name": "Ananya",
                "last_name": "Sharma",
                "email": "ananya.sharma@helperlearner.in",
                "bio": "Backend engineer in Bengaluru focused on fintech APIs and reliability.",
                "knowledge_points": 260,
                "wallet_inr": "48500.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 36,
                "skills": ["Python", "Django", "Django REST", "PostgreSQL", "System Design"],
            },
            {
                "username": "rohan_mehta",
                "first_name": "Rohan",
                "last_name": "Mehta",
                "email": "rohan.mehta@helperlearner.in",
                "bio": "Product-minded engineer building UPI and recurring payment workflows.",
                "knowledge_points": 220,
                "wallet_inr": "36200.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 18,
                "skills": ["Python", "Django REST", "System Design", "Cybersecurity"],
            },
            {
                "username": "priya_nair",
                "first_name": "Priya",
                "last_name": "Nair",
                "email": "priya.nair@helperlearner.in",
                "bio": "Full-stack developer in Kochi working on commerce and deployment pipelines.",
                "knowledge_points": 210,
                "wallet_inr": "30100.00",
                "compliance_verified": True,
                "notification_preference": "in_app",
                "ui_density": "comfortable",
                "claim_hours_ago": 30,
                "skills": ["Django", "React", "Docker", "DevOps"],
            },
            {
                "username": "vivek_iyer",
                "first_name": "Vivek",
                "last_name": "Iyer",
                "email": "vivek.iyer@helperlearner.in",
                "bio": "API specialist from Chennai with strong DRF and Postgres optimization experience.",
                "knowledge_points": 190,
                "wallet_inr": "18400.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 26,
                "skills": ["Django", "Django REST", "PostgreSQL", "Testing"],
            },
            {
                "username": "neha_gupta",
                "first_name": "Neha",
                "last_name": "Gupta",
                "email": "neha.gupta@helperlearner.in",
                "bio": "QA automation lead in Noida, focused on stable CI pipelines.",
                "knowledge_points": 175,
                "wallet_inr": "11600.00",
                "compliance_verified": True,
                "notification_preference": "email",
                "ui_density": "comfortable",
                "claim_hours_ago": 42,
                "skills": ["Testing", "Python", "Django", "DevOps"],
            },
            {
                "username": "arjun_verma",
                "first_name": "Arjun",
                "last_name": "Verma",
                "email": "arjun.verma@helperlearner.in",
                "bio": "Platform engineer in Pune with deep Celery and background-worker expertise.",
                "knowledge_points": 205,
                "wallet_inr": "15200.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 16,
                "skills": ["Python", "Redis", "DevOps", "Docker", "AWS"],
            },
            {
                "username": "isha_kapoor",
                "first_name": "Isha",
                "last_name": "Kapoor",
                "email": "isha.kapoor@helperlearner.in",
                "bio": "React and UX engineer in Gurgaon building role-based dashboards.",
                "knowledge_points": 185,
                "wallet_inr": "22800.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 28,
                "skills": ["React", "Next.js", "UI/UX", "Testing"],
            },
            {
                "username": "karan_malhotra",
                "first_name": "Karan",
                "last_name": "Malhotra",
                "email": "karan.malhotra@helperlearner.in",
                "bio": "Engineering manager in Delhi handling payment orchestration systems.",
                "knowledge_points": 240,
                "wallet_inr": "40200.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 55,
                "skills": ["System Design", "Python", "Django REST", "AWS"],
            },
            {
                "username": "sneha_patil",
                "first_name": "Sneha",
                "last_name": "Patil",
                "email": "sneha.patil@helperlearner.in",
                "bio": "DevOps-minded full stack dev from Mumbai handling Docker/Render rollouts.",
                "knowledge_points": 170,
                "wallet_inr": "26800.00",
                "compliance_verified": True,
                "notification_preference": "in_app",
                "ui_density": "compact",
                "claim_hours_ago": 40,
                "skills": ["DevOps", "Docker", "Django", "AWS"],
            },
            {
                "username": "aditya_kulkarni",
                "first_name": "Aditya",
                "last_name": "Kulkarni",
                "email": "aditya.kulkarni@helperlearner.in",
                "bio": "Senior QA + backend engineer who debugs flaky test infrastructure.",
                "knowledge_points": 165,
                "wallet_inr": "12100.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 33,
                "skills": ["Testing", "Python", "Django REST"],
            },
            {
                "username": "kavya_reddy",
                "first_name": "Kavya",
                "last_name": "Reddy",
                "email": "kavya.reddy@helperlearner.in",
                "bio": "Frontend lead in Hyderabad building checkout and admin UX.",
                "knowledge_points": 195,
                "wallet_inr": "34100.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 29,
                "skills": ["React", "Next.js", "UI/UX", "Prompt Engineering"],
            },
            {
                "username": "manish_yadav",
                "first_name": "Manish",
                "last_name": "Yadav",
                "email": "manish.yadav@helperlearner.in",
                "bio": "Analytics engineer in Indore handling data cleanup and reporting pipelines.",
                "knowledge_points": 140,
                "wallet_inr": "9600.00",
                "compliance_verified": True,
                "notification_preference": "email",
                "ui_density": "comfortable",
                "claim_hours_ago": 50,
                "skills": ["Data Engineering", "Python", "PostgreSQL"],
            },
            {
                "username": "ritu_singh",
                "first_name": "Ritu",
                "last_name": "Singh",
                "email": "ritu.singh@helperlearner.in",
                "bio": "Backend dev from Jaipur interested in secure auth and API design.",
                "knowledge_points": 150,
                "wallet_inr": "13250.00",
                "compliance_verified": False,
                "notification_preference": "in_app",
                "ui_density": "comfortable",
                "claim_hours_ago": 21,
                "skills": ["Django REST", "Cybersecurity", "Python"],
            },
            {
                "username": "devansh_jain",
                "first_name": "Devansh",
                "last_name": "Jain",
                "email": "devansh.jain@helperlearner.in",
                "bio": "Senior backend engineer in Ahmedabad focused on abuse prevention and rate limiting.",
                "knowledge_points": 180,
                "wallet_inr": "28400.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 47,
                "skills": ["Python", "Cybersecurity", "Django", "System Design"],
            },
            {
                "username": "pooja_chawla",
                "first_name": "Pooja",
                "last_name": "Chawla",
                "email": "pooja.chawla@helperlearner.in",
                "bio": "Operations-focused tech lead in Chandigarh with strong incident response skills.",
                "knowledge_points": 165,
                "wallet_inr": "22600.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 24,
                "skills": ["DevOps", "Cybersecurity", "Docker"],
            },
            {
                "username": "harshit_saxena",
                "first_name": "Harshit",
                "last_name": "Saxena",
                "email": "harshit.saxena@helperlearner.in",
                "bio": "Security engineer in Lucknow solving auth throttling and abuse issues.",
                "knowledge_points": 172,
                "wallet_inr": "10400.00",
                "compliance_verified": False,
                "notification_preference": "in_app",
                "ui_density": "compact",
                "claim_hours_ago": 20,
                "skills": ["Cybersecurity", "Python", "Django"],
            },
            {
                "username": "tanvi_bansal",
                "first_name": "Tanvi",
                "last_name": "Bansal",
                "email": "tanvi.bansal@helperlearner.in",
                "bio": "API performance engineer in Nagpur working on Redis and catalog scaling.",
                "knowledge_points": 188,
                "wallet_inr": "15800.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "comfortable",
                "claim_hours_ago": 31,
                "skills": ["Redis", "Django REST", "PostgreSQL"],
            },
            {
                "username": "farhan_ali",
                "first_name": "Farhan",
                "last_name": "Ali",
                "email": "farhan.ali@helperlearner.in",
                "bio": "Freelance backend consultant in Bhopal working on caching and API hardening.",
                "knowledge_points": 212,
                "wallet_inr": "24300.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 34,
                "skills": ["Redis", "Django REST", "Python", "PostgreSQL"],
            },
            {
                "username": "megha_joshi",
                "first_name": "Megha",
                "last_name": "Joshi",
                "email": "megha.joshi@helperlearner.in",
                "bio": "Product engineer in Surat balancing frontend quality with mobile performance.",
                "knowledge_points": 160,
                "wallet_inr": "11900.00",
                "compliance_verified": True,
                "notification_preference": "email",
                "ui_density": "comfortable",
                "claim_hours_ago": 37,
                "skills": ["React", "Flutter", "UI/UX"],
            },
            {
                "username": "siddharth_rao",
                "first_name": "Siddharth",
                "last_name": "Rao",
                "email": "siddharth.rao@helperlearner.in",
                "bio": "Cloud/DevOps engineer in Mangalore automating reliable production deployments.",
                "knowledge_points": 200,
                "wallet_inr": "27100.00",
                "compliance_verified": True,
                "notification_preference": "both",
                "ui_density": "compact",
                "claim_hours_ago": 60,
                "skills": ["DevOps", "Docker", "AWS", "System Design"],
            },
            {
                "username": "nikhil_banerjee",
                "first_name": "Nikhil",
                "last_name": "Banerjee",
                "email": "nikhil.banerjee@helperlearner.in",
                "bio": "Data platform engineer in Kolkata focusing on ETL and query tuning.",
                "knowledge_points": 176,
                "wallet_inr": "14300.00",
                "compliance_verified": True,
                "notification_preference": "in_app",
                "ui_density": "comfortable",
                "claim_hours_ago": 32,
                "skills": ["Data Engineering", "PostgreSQL", "AWS"],
            },
            {
                "username": "diya_menon",
                "first_name": "Diya",
                "last_name": "Menon",
                "email": "diya.menon@helperlearner.in",
                "bio": "ML engineer in Thiruvananthapuram building multilingual relevance and ranking systems.",
                "knowledge_points": 183,
                "wallet_inr": "16750.00",
                "compliance_verified": True,
                "notification_preference": "none",
                "ui_density": "comfortable",
                "claim_hours_ago": 45,
                "skills": ["Machine Learning", "Python", "Prompt Engineering", "Search"],
            },
        ]

        user_map = {}
        for spec in user_specs:
            user = CustomUser.objects.create_user(
                username=spec["username"],
                email=spec["email"],
                password=password,
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                bio=spec["bio"],
                knowledge_points=spec["knowledge_points"],
                wallet_inr=Decimal(spec["wallet_inr"]),
                compliance_verified=spec["compliance_verified"],
                notification_preference=spec["notification_preference"],
                ui_density=spec["ui_density"],
            )
            claim_hours = spec.get("claim_hours_ago")
            if claim_hours:
                user.last_kp_claim = now - timedelta(hours=claim_hours)
                user.save(update_fields=["last_kp_claim"])
            user.skills.set([skills[name] for name in spec["skills"]])
            user_map[spec["username"]] = user
        return user_map

    def _create_help_requests(self, users, skills, tags, now):
        request_specs = [
            {
                "key": "railway_500",
                "poster": "priya_nair",
                "skill": "Django",
                "title": "Django 500 after Railway deploy with static files",
                "description": (
                    "Staging build passes, but production throws 500 on /browse/ right after collectstatic. "
                    "Need help fixing WhiteNoise + manifest static handling and tracing missing assets."
                ),
                "kp": 36,
                "status": "open",
                "tags": ["django", "deployment", "docker", "production"],
                "days_ago": 1,
                "updated_hours": 6,
            },
            {
                "key": "upi_webhook",
                "poster": "rohan_mehta",
                "skill": "Python",
                "title": "UPI webhook signature verification mismatch in FastAPI gateway",
                "description": (
                    "Razorpay/UPI callback signatures fail intermittently when payload has escaped unicode. "
                    "Need a replay-safe verifier and consistent audit logs."
                ),
                "kp": 48,
                "status": "open",
                "tags": ["upi", "payments", "api", "security"],
                "days_ago": 2,
                "updated_hours": 10,
            },
            {
                "key": "react_state",
                "poster": "kavya_reddy",
                "skill": "React",
                "title": "React checkout form resets on route change in Next.js",
                "description": (
                    "Checkout form state clears when address modal opens and route changes. "
                    "Need stable state flow without introducing heavy global state boilerplate."
                ),
                "kp": 28,
                "status": "open",
                "tags": ["react", "frontend", "debugging"],
                "days_ago": 1,
                "updated_hours": 8,
            },
            {
                "key": "pg_report",
                "poster": "manish_yadav",
                "skill": "PostgreSQL",
                "title": "PostgreSQL monthly sales report query is too slow",
                "description": (
                    "Monthly report query takes ~18 seconds on 2M rows. Need indexing + query rewrite strategy "
                    "based on explain analyze output."
                ),
                "kp": 42,
                "status": "open",
                "tags": ["database", "performance", "analytics"],
                "days_ago": 3,
                "updated_hours": 5,
            },
            {
                "key": "drf_gst",
                "poster": "ananya_sharma",
                "helper": "vivek_iyer",
                "skill": "Django REST",
                "title": "DRF validation for GST invoice create API",
                "description": (
                    "Need serializer validation for GSTIN + HSN combos and state-wise tax split rules before "
                    "invoice records are saved."
                ),
                "kp": 34,
                "status": "in_progress",
                "tags": ["api", "gst", "validation"],
                "days_ago": 5,
                "updated_hours": 86,
            },
            {
                "key": "celery_retry",
                "poster": "karan_malhotra",
                "helper": "arjun_verma",
                "skill": "Python",
                "title": "Celery retries for payment status sync are creating duplicates",
                "description": (
                    "Retries after timeout are creating duplicate reconciliation rows. Need idempotency key design "
                    "and locking strategy."
                ),
                "kp": 52,
                "status": "in_progress",
                "tags": ["payments", "debugging", "backend"],
                "days_ago": 6,
                "updated_hours": 90,
            },
            {
                "key": "pytest_flaky",
                "poster": "neha_gupta",
                "helper": "aditya_kulkarni",
                "skill": "Testing",
                "title": "Fix flaky pytest suite in CI for notification flows",
                "description": (
                    "Tests randomly fail in GitHub Actions around timestamps and timezone conversions. "
                    "Need deterministic fixtures and cleanup strategy."
                ),
                "kp": 24,
                "status": "resolved",
                "tags": ["testing", "ci", "debugging"],
                "days_ago": 10,
                "updated_hours": 200,
            },
            {
                "key": "docker_nginx",
                "poster": "sneha_patil",
                "helper": "siddharth_rao",
                "skill": "DevOps",
                "title": "Dockerize Django + Nginx with health checks for Render",
                "description": (
                    "Need production-grade Docker + Nginx setup with /healthz, static routing, and graceful "
                    "rollout behavior."
                ),
                "kp": 44,
                "status": "resolved",
                "tags": ["docker", "deployment", "devops"],
                "days_ago": 12,
                "updated_hours": 240,
            },
            {
                "key": "rbac_dashboard",
                "poster": "kavya_reddy",
                "helper": "isha_kapoor",
                "skill": "React",
                "title": "Role-based UI auth in React admin dashboard",
                "description": (
                    "Need route guards and feature-level access checks for admin/support/seller roles with "
                    "clean maintainable architecture."
                ),
                "kp": 54,
                "status": "resolved",
                "tags": ["react", "authentication", "frontend"],
                "days_ago": 9,
                "updated_hours": 180,
            },
            {
                "key": "redis_cache",
                "poster": "tanvi_bansal",
                "helper": "farhan_ali",
                "skill": "Redis",
                "title": "Set up Redis caching for product catalog API",
                "description": (
                    "Need cache-aside strategy, invalidation hooks on catalog changes, and hit-ratio telemetry."
                ),
                "kp": 31,
                "status": "resolved",
                "tags": ["redis", "performance", "api"],
                "days_ago": 8,
                "updated_hours": 170,
            },
            {
                "key": "pandas_cleanup",
                "poster": "manish_yadav",
                "skill": "Data Engineering",
                "title": "Pandas cleanup for messy vendor sales CSV exports",
                "description": (
                    "Need robust cleanup for mixed date formats, duplicate SKUs, and null tax slabs before loading "
                    "to reporting DB."
                ),
                "kp": 22,
                "status": "canceled",
                "tags": ["analytics", "data", "python"],
                "days_ago": 14,
                "updated_hours": 250,
            },
            {
                "key": "otp_throttle",
                "poster": "pooja_chawla",
                "helper": "harshit_saxena",
                "skill": "Cybersecurity",
                "title": "OTP SMS throttle bug causing delayed logins",
                "description": (
                    "Throttle middleware blocks legitimate retries during telecom delays. Need safer limits and "
                    "fallback handling."
                ),
                "kp": 29,
                "status": "canceled",
                "tags": ["authentication", "security", "backend"],
                "days_ago": 7,
                "updated_hours": 120,
            },
            {
                "key": "search_ranking",
                "poster": "diya_menon",
                "skill": "Machine Learning",
                "title": "Improve search ranking for Hindi + English mixed queries",
                "description": (
                    "Search ranking is weak for Hinglish terms. Need tokenizer/normalizer tuning and practical "
                    "weighting strategy."
                ),
                "kp": 38,
                "status": "open",
                "tags": ["search", "ai", "analytics"],
                "days_ago": 2,
                "updated_hours": 7,
            },
        ]

        req_map = {}
        for spec in request_specs:
            req = HelpRequest.objects.create(
                title=spec["title"],
                description=spec["description"],
                user=users[spec["poster"]],
                skill_needed=skills[spec["skill"]],
                kp_bounty=spec["kp"],
                status=spec["status"],
                accepted_by=users.get(spec.get("helper")) if spec.get("helper") else None,
            )
            req.tags.set([tags[name] for name in spec["tags"]])
            created_at = now - timedelta(days=spec["days_ago"])
            updated_at = created_at + timedelta(hours=spec["updated_hours"])
            expires_at = created_at + timedelta(days=7)
            HelpRequest.objects.filter(pk=req.pk).update(
                created_at=created_at,
                updated_at=updated_at,
                expires_at=expires_at,
            )
            req.refresh_from_db()
            req_map[spec["key"]] = req
        return req_map

    def _create_help_request_proposals(self, requests, users, now):
        proposal_specs = [
            ("railway_500", "siddharth_rao", 30, "pending", "Can fix this with a reproducible static-manifest check.", 18),
            ("railway_500", "vivek_iyer", 32, "pending", "I can debug WhiteNoise pipeline and patch settings.", 16),
            ("railway_500", "arjun_verma", 34, "withdrawn", "Happy to take this if needed.", 14),
            ("upi_webhook", "farhan_ali", 40, "pending", "Handled this exact signature mismatch before.", 20),
            ("upi_webhook", "aditya_kulkarni", 44, "pending", "Can build reliable verifier + tests.", 17),
            ("react_state", "isha_kapoor", 24, "pending", "I can refactor route state persistence cleanly.", 15),
            ("react_state", "megha_joshi", 26, "pending", "Can solve with scoped context + tests.", 13),
            ("pg_report", "nikhil_banerjee", 35, "pending", "Will optimize using partial indexes and query rewrite.", 12),
            ("pg_report", "devansh_jain", 38, "pending", "Can tune this with execution-plan driven changes.", 11),
            ("search_ranking", "nikhil_banerjee", 33, "pending", "Can improve ranking via weighted token expansion.", 10),
            ("search_ranking", "megha_joshi", 36, "pending", "Can tune bilingual normalization strategy.", 9),
            ("drf_gst", "vivek_iyer", 30, "selected", "Will add schema-safe validation and exhaustive tests.", 96),
            ("drf_gst", "farhan_ali", 33, "rejected", "Can also support GST edge cases.", 94),
            ("celery_retry", "arjun_verma", 48, "selected", "I will implement idempotency + lock key approach.", 100),
            ("celery_retry", "siddharth_rao", 50, "rejected", "Can handle retry orchestration quickly.", 97),
            ("pytest_flaky", "aditya_kulkarni", 22, "selected", "Will stabilize fixtures and clock handling.", 190),
            ("pytest_flaky", "devansh_jain", 24, "rejected", "Can review CI and race conditions.", 186),
            ("docker_nginx", "siddharth_rao", 40, "selected", "Can deliver hardened deployment setup.", 220),
            ("docker_nginx", "arjun_verma", 43, "rejected", "Can set up docker and Nginx quickly.", 216),
            ("rbac_dashboard", "isha_kapoor", 50, "selected", "Will ship role matrices + guard tests.", 170),
            ("rbac_dashboard", "megha_joshi", 53, "rejected", "Can do this with route-level ACLs.", 166),
            ("redis_cache", "farhan_ali", 28, "selected", "Will add cache keys + invalidation patterns.", 168),
            ("redis_cache", "vivek_iyer", 30, "rejected", "Can optimize cache and DB fallback.", 164),
            ("pandas_cleanup", "nikhil_banerjee", 19, "withdrawn", "Can build robust cleanup pipeline.", 230),
            ("otp_throttle", "harshit_saxena", 27, "selected", "Will redesign throttle windows safely.", 110),
        ]

        created = []
        for req_key, applicant_key, proposed_kp, status, note, hours_ago in proposal_specs:
            request_obj = requests[req_key]
            proposal = HelpRequestProposal.objects.create(
                request=request_obj,
                applicant=users[applicant_key],
                proposed_kp=proposed_kp,
                status=status,
                cover_note=note,
                selected_at=(now - timedelta(hours=hours_ago - 1)) if status == "selected" else None,
            )
            proposal_created = now - timedelta(hours=hours_ago)
            HelpRequestProposal.objects.filter(pk=proposal.pk).update(
                created_at=proposal_created,
                updated_at=proposal_created + timedelta(minutes=40),
            )
            created.append(proposal)
        return created

    def _create_request_comments(self, requests, users, now):
        comment_specs = [
            ("railway_500", "siddharth_rao", "Can you share your `STATICFILES_STORAGE` and `collectstatic` log output?", False, 18),
            ("upi_webhook", "farhan_ali", "Please confirm if payload is raw-body or JSON-normalized before HMAC.", False, 14),
            ("react_state", "isha_kapoor", "This usually happens when modal route remounts parent state.", False, 10),
            ("pg_report", "nikhil_banerjee", "Share explain plan; we can likely remove one costly hash aggregate.", False, 16),
            ("drf_gst", "ananya_sharma", "I uploaded 3 failing payload examples in the comments above.", True, 60),
            ("drf_gst", "vivek_iyer", "Got it, I am adding field-level GSTIN + place-of-supply checks.", True, 58),
            ("celery_retry", "karan_malhotra", "Please make sure retries do not duplicate ledger rows.", True, 74),
            ("celery_retry", "arjun_verma", "Implemented idempotency key with Redis lock, validating now.", True, 70),
            ("pytest_flaky", "neha_gupta", "Perfect fix. CI has been green for 6 consecutive runs.", False, 145),
            ("docker_nginx", "sneha_patil", "Deployment is stable now, rolling this to production tonight.", False, 160),
            ("rbac_dashboard", "kavya_reddy", "Feature-flag based role mapping works great. Thanks!", False, 132),
            ("redis_cache", "tanvi_bansal", "Hit ratio moved from 34% to 81% after your changes.", False, 128),
            ("otp_throttle", "pooja_chawla", "Canceling this for now while telecom vendor updates SLA.", True, 95),
        ]
        for req_key, user_key, content, is_private, hours_ago in comment_specs:
            comment = Comment.objects.create(
                request=requests[req_key],
                user=users[user_key],
                content=content,
                is_private=is_private,
            )
            Comment.objects.filter(pk=comment.pk).update(created_at=now - timedelta(hours=hours_ago))

    def _create_ratings(self, requests, users, now):
        rating_specs = [
            ("pytest_flaky", "neha_gupta", "aditya_kulkarni", 5, 140),
            ("docker_nginx", "sneha_patil", "siddharth_rao", 4, 150),
            ("rbac_dashboard", "kavya_reddy", "isha_kapoor", 5, 120),
            ("redis_cache", "tanvi_bansal", "farhan_ali", 4, 118),
        ]
        for req_key, by_user, to_user, score, hours_ago in rating_specs:
            rating = Rating.objects.create(
                request=requests[req_key],
                given_by=users[by_user],
                given_to=users[to_user],
                score=score,
            )
            Rating.objects.filter(pk=rating.pk).update(created_at=now - timedelta(hours=hours_ago))

    def _create_saved_searches(self, users, skills, tags, now):
        search_specs = [
            ("rohan_mehta", "upi webhook", "Python", "upi", True, 12),
            ("priya_nair", "deployment", "DevOps", "deployment", True, 18),
            ("neha_gupta", "", "Testing", "debugging", True, 30),
            ("tanvi_bansal", "redis cache", "Redis", "redis", False, 45),
            ("diya_menon", "hinglish search", "Machine Learning", "search", True, 20),
            ("arjun_verma", "celery retries", "Python", "backend", True, 26),
            ("isha_kapoor", "role based", "React", "frontend", True, 22),
            ("siddharth_rao", "", "DevOps", "docker", True, 36),
        ]
        for user_key, query, skill_key, tag_key, is_active, notified_hours_ago in search_specs:
            search = SavedSearch.objects.create(
                user=users[user_key],
                query=query,
                skill=skills.get(skill_key),
                tag=tags.get(tag_key),
                is_active=is_active,
                last_notified_at=now - timedelta(hours=notified_hours_ago),
            )
            SavedSearch.objects.filter(pk=search.pk).update(created_at=now - timedelta(hours=notified_hours_ago + 6))

    def _create_jobs_and_milestones(self, users, skills, tags, now):
        job_specs = [
            {
                "key": "gst_pdf_service",
                "client": "rohan_mehta",
                "skill": "Django",
                "title": "Build GST-ready invoice PDF microservice",
                "description": "Need robust invoice rendering with GST-compliant format, QR support, and signed output.",
                "budget": "18000.00",
                "escrow": "18000.00",
                "status": "open",
                "tags": ["gst", "api", "invoices", "backend"],
                "days_ago": 2,
                "updated_hours": 18,
            },
            {
                "key": "mysql_to_postgres",
                "client": "ananya_sharma",
                "skill": "PostgreSQL",
                "title": "Migrate legacy MySQL reporting workload to PostgreSQL",
                "description": "Need migration plan + query parity checks + index strategy for monthly report jobs.",
                "budget": "24000.00",
                "escrow": "24000.00",
                "status": "open",
                "tags": ["database", "performance", "analytics", "data"],
                "days_ago": 4,
                "updated_hours": 30,
            },
            {
                "key": "flutter_crashlytics",
                "client": "sneha_patil",
                "skill": "Flutter",
                "title": "Flutter app crash analytics integration and triage setup",
                "description": "Set up Crashlytics + release channel tagging + issue severity routing.",
                "budget": "15000.00",
                "escrow": "15000.00",
                "status": "open",
                "tags": ["flutter", "mobile", "debugging"],
                "days_ago": 1,
                "updated_hours": 12,
            },
            {
                "key": "ondc_sync",
                "client": "karan_malhotra",
                "freelancer": "arjun_verma",
                "skill": "Python",
                "title": "Implement ONDC catalog sync pipeline",
                "description": "Need a reliable catalog delta sync with retries, monitoring, and replay safety.",
                "budget": "30000.00",
                "escrow": "18000.00",
                "status": "in_progress",
                "tags": ["api", "backend", "performance"],
                "days_ago": 9,
                "updated_hours": 120,
            },
            {
                "key": "multilingual_storefront",
                "client": "priya_nair",
                "freelancer": "isha_kapoor",
                "skill": "React",
                "title": "Add multilingual support in React storefront",
                "description": "Implement i18n for English/Hindi/Tamil with locale-aware routing and SEO tags.",
                "budget": "22000.00",
                "escrow": "0.00",
                "status": "completed",
                "tags": ["react", "frontend", "performance"],
                "days_ago": 15,
                "updated_hours": 310,
            },
            {
                "key": "ratelimit_revamp",
                "client": "devansh_jain",
                "freelancer": "farhan_ali",
                "skill": "Cybersecurity",
                "title": "API rate limiting and abuse monitoring revamp",
                "description": "Need layered rate-limits with tenant exceptions, abuse score, and alerting.",
                "budget": "25000.00",
                "escrow": "12000.00",
                "status": "disputed",
                "tags": ["security", "api", "performance"],
                "days_ago": 11,
                "updated_hours": 210,
            },
            {
                "key": "bigquery_pipeline",
                "client": "kavya_reddy",
                "freelancer": "nikhil_banerjee",
                "skill": "Data Engineering",
                "title": "Set up BigQuery warehouse pipeline for daily BI dashboards",
                "description": "Need ingestion DAG + schema evolution handling + cost controls.",
                "budget": "28000.00",
                "escrow": "0.00",
                "status": "canceled",
                "tags": ["data", "analytics", "database"],
                "days_ago": 13,
                "updated_hours": 260,
            },
            {
                "key": "k8s_observability",
                "client": "pooja_chawla",
                "freelancer": "siddharth_rao",
                "skill": "DevOps",
                "title": "Kubernetes observability stack hardening",
                "description": "Improve logs/metrics/tracing pipeline with alert routing and SLO dashboards.",
                "budget": "19000.00",
                "escrow": "9500.00",
                "status": "in_progress",
                "tags": ["devops", "docker", "performance"],
                "days_ago": 7,
                "updated_hours": 135,
            },
        ]

        job_map = {}
        for spec in job_specs:
            job = FreelanceJob.objects.create(
                title=spec["title"],
                description=spec["description"],
                client=users[spec["client"]],
                freelancer=users.get(spec.get("freelancer")) if spec.get("freelancer") else None,
                skill_needed=skills[spec["skill"]],
                budget_inr=Decimal(spec["budget"]),
                escrow_inr=Decimal(spec["escrow"]),
                status=spec["status"],
                payment_type="fixed",
            )
            job.tags.set([tags[name] for name in spec["tags"]])
            created_at = now - timedelta(days=spec["days_ago"])
            updated_at = created_at + timedelta(hours=spec["updated_hours"])
            FreelanceJob.objects.filter(pk=job.pk).update(created_at=created_at, updated_at=updated_at)
            job.refresh_from_db()
            job_map[spec["key"]] = job

        milestone_specs = [
            ("ondc_sync", 1, "Schema mapping + ONDC adapter", "12000.00", "released", 168, 158),
            ("ondc_sync", 2, "Delta sync worker + retries", "10000.00", "submitted", 120, None),
            ("ondc_sync", 3, "Ops runbook + alerting", "8000.00", "pending", None, None),
            ("multilingual_storefront", 1, "Locale infra and routing", "10000.00", "released", 290, 280),
            ("multilingual_storefront", 2, "Translations and QA", "7000.00", "released", 275, 265),
            ("multilingual_storefront", 3, "SEO and language switch UX", "5000.00", "released", 260, 250),
            ("ratelimit_revamp", 1, "Traffic fingerprinting + baseline rules", "13000.00", "released", 200, 192),
            ("ratelimit_revamp", 2, "Tenant override policy engine", "7000.00", "disputed", 186, None),
            ("ratelimit_revamp", 3, "Incident dashboard + alerts", "5000.00", "pending", None, None),
            ("k8s_observability", 1, "Prometheus + Grafana baseline", "9500.00", "released", 110, 102),
            ("k8s_observability", 2, "Tracing and alert policy tuning", "9500.00", "submitted", 96, None),
            ("bigquery_pipeline", 1, "Ingestion DAG prototype", "14000.00", "pending", None, None),
        ]

        milestone_map = {}
        for job_key, sequence, title, amount, status, submitted_hrs, released_hrs in milestone_specs:
            milestone = JobMilestone.objects.create(
                job=job_map[job_key],
                sequence=sequence,
                title=title,
                amount_inr=Decimal(amount),
                status=status,
                submitted_at=(now - timedelta(hours=submitted_hrs)) if submitted_hrs else None,
                released_at=(now - timedelta(hours=released_hrs)) if released_hrs else None,
            )
            milestone_map[f"{job_key}_m{sequence}"] = milestone
        return job_map, milestone_map

    def _create_job_proposals(self, jobs, users, now):
        proposal_specs = [
            ("gst_pdf_service", "vivek_iyer", "16500.00", "pending", "Will deliver GST template engine + signed PDF output.", 48),
            ("gst_pdf_service", "siddharth_rao", "17200.00", "pending", "Can build with wkhtmltopdf fallback and audit logs.", 44),
            ("gst_pdf_service", "farhan_ali", "17600.00", "withdrawn", "Happy to pick this up if timeline is flexible.", 41),
            ("mysql_to_postgres", "nikhil_banerjee", "22000.00", "pending", "Migration with rollbacks and query parity checks.", 72),
            ("mysql_to_postgres", "aditya_kulkarni", "23000.00", "pending", "Can handle schema migration plus CI SQL tests.", 69),
            ("flutter_crashlytics", "megha_joshi", "13800.00", "pending", "Will wire Crashlytics with release tagging.", 20),
            ("flutter_crashlytics", "tanvi_bansal", "14500.00", "pending", "Can set triage with severity labels.", 18),
            ("ondc_sync", "arjun_verma", "30000.00", "selected", "Will build idempotent pipeline with replay safety.", 180),
            ("ondc_sync", "farhan_ali", "29500.00", "rejected", "Can deliver similar architecture quickly.", 176),
            ("multilingual_storefront", "isha_kapoor", "22000.00", "selected", "I can ship complete i18n + SEO flow.", 320),
            ("multilingual_storefront", "megha_joshi", "21800.00", "rejected", "Can handle localization and QA.", 316),
            ("ratelimit_revamp", "farhan_ali", "25000.00", "selected", "Will design layered limits and abuse scoring.", 235),
            ("ratelimit_revamp", "arjun_verma", "25200.00", "rejected", "Can implement Redis-backed dynamic throttling.", 232),
            ("bigquery_pipeline", "nikhil_banerjee", "26000.00", "selected", "Can set up ingestion DAGs with checks.", 290),
            ("k8s_observability", "siddharth_rao", "19000.00", "selected", "Can complete monitoring hardening in phases.", 150),
            ("k8s_observability", "vivek_iyer", "18800.00", "rejected", "Can support this if needed.", 147),
        ]
        for job_key, applicant_key, proposed_total, status, note, hours_ago in proposal_specs:
            proposal = FreelanceJobProposal.objects.create(
                job=jobs[job_key],
                applicant=users[applicant_key],
                proposed_total_inr=Decimal(proposed_total),
                status=status,
                cover_note=note,
                selected_at=(now - timedelta(hours=hours_ago - 2)) if status == "selected" else None,
            )
            created_at = now - timedelta(hours=hours_ago)
            FreelanceJobProposal.objects.filter(pk=proposal.pk).update(
                created_at=created_at,
                updated_at=created_at + timedelta(minutes=30),
            )
            for title, amount, sequence in self._proposal_milestone_plan(job_key, applicant_key):
                FreelanceJobProposalMilestone.objects.create(
                    proposal=proposal,
                    title=title,
                    amount_inr=Decimal(amount),
                    sequence=sequence,
                )

    def _proposal_milestone_plan(self, job_key, applicant_key):
        plans = {
            ("gst_pdf_service", "vivek_iyer"): [
                ("Template + tax engine", "8500.00", 1),
                ("Signed PDF + QR checks", "8000.00", 2),
            ],
            ("gst_pdf_service", "siddharth_rao"): [
                ("PDF rendering service", "9000.00", 1),
                ("Signature + monitoring", "8200.00", 2),
            ],
            ("mysql_to_postgres", "nikhil_banerjee"): [
                ("Schema migration", "12000.00", 1),
                ("Query tuning + validation", "10000.00", 2),
            ],
            ("mysql_to_postgres", "aditya_kulkarni"): [
                ("Migration script pack", "11000.00", 1),
                ("Testing + cutover runbook", "12000.00", 2),
            ],
            ("flutter_crashlytics", "megha_joshi"): [
                ("Crashlytics setup", "7000.00", 1),
                ("Triage workflow + docs", "6800.00", 2),
            ],
            ("flutter_crashlytics", "tanvi_bansal"): [
                ("SDK + release channels", "7600.00", 1),
                ("Alerting and dashboards", "6900.00", 2),
            ],
        }
        return plans.get((job_key, applicant_key), [])

    def _create_disputes(self, jobs, users, now):
        dispute_specs = [
            {
                "job": "ratelimit_revamp",
                "opened_by": "devansh_jain",
                "against": "farhan_ali",
                "reason": "Milestone 2 did not include tenant-specific override exceptions promised in scope.",
                "status": "open",
                "resolution_type": "",
                "refund_amount_inr": "0.00",
                "payout_amount_inr": "0.00",
                "resolution_note": "",
                "resolved_by": None,
                "created_hours_ago": 72,
                "resolved_hours_ago": None,
            },
            {
                "job": "bigquery_pipeline",
                "opened_by": "kavya_reddy",
                "against": "nikhil_banerjee",
                "reason": "Client paused scope after internal vendor switch. Requested escrow refund.",
                "status": "resolved",
                "resolution_type": "refund_client",
                "refund_amount_inr": "28000.00",
                "payout_amount_inr": "0.00",
                "resolution_note": "Client refunded after cancellation and mutual closure.",
                "resolved_by": "ananya_sharma",
                "created_hours_ago": 190,
                "resolved_hours_ago": 168,
            },
        ]
        created = []
        for spec in dispute_specs:
            dispute = JobDispute.objects.create(
                job=jobs[spec["job"]],
                opened_by=users[spec["opened_by"]],
                against_user=users[spec["against"]],
                reason=spec["reason"],
                status=spec["status"],
                resolution_type=spec["resolution_type"],
                refund_amount_inr=Decimal(spec["refund_amount_inr"]),
                payout_amount_inr=Decimal(spec["payout_amount_inr"]),
                resolution_note=spec["resolution_note"],
                resolved_by=users.get(spec["resolved_by"]) if spec["resolved_by"] else None,
                resolved_at=(now - timedelta(hours=spec["resolved_hours_ago"])) if spec["resolved_hours_ago"] else None,
            )
            created_at = now - timedelta(hours=spec["created_hours_ago"])
            JobDispute.objects.filter(pk=dispute.pk).update(
                created_at=created_at,
                updated_at=created_at + timedelta(hours=1),
            )
            created.append(dispute)
        return created

    def _create_wallet_and_payout_data(self, jobs, milestones, users, now):
        ledger_specs = [
            ("rohan_mehta", "debit", "18000.00", "job_escrow", jobs["gst_pdf_service"].pk, "Escrow funded for job posting", 48),
            ("ananya_sharma", "debit", "24000.00", "job_escrow", jobs["mysql_to_postgres"].pk, "Escrow funded for migration project", 72),
            ("sneha_patil", "debit", "15000.00", "job_escrow", jobs["flutter_crashlytics"].pk, "Escrow funded for mobile reliability project", 20),
            ("karan_malhotra", "debit", "30000.00", "job_escrow", jobs["ondc_sync"].pk, "Escrow funded for ONDC sync work", 180),
            ("priya_nair", "debit", "22000.00", "job_escrow", jobs["multilingual_storefront"].pk, "Escrow funded for storefront localization", 320),
            ("devansh_jain", "debit", "26000.00", "job_escrow", jobs["ratelimit_revamp"].pk, "Escrow funded for rate-limit revamp", 235),
            ("devansh_jain", "credit", "1000.00", "job_bid_refund", jobs["ratelimit_revamp"].pk, "Escrow adjustment after selecting lower bid", 232),
            ("kavya_reddy", "debit", "28000.00", "job_escrow", jobs["bigquery_pipeline"].pk, "Escrow funded for warehouse setup", 290),
            ("kavya_reddy", "credit", "28000.00", "job_escrow_refund", jobs["bigquery_pipeline"].pk, "Escrow refunded after cancellation", 168),
            ("pooja_chawla", "debit", "19000.00", "job_escrow", jobs["k8s_observability"].pk, "Escrow funded for observability hardening", 150),
            ("arjun_verma", "credit", "12000.00", "job_milestone_release", milestones["ondc_sync_m1"].pk, "Milestone release for ONDC pipeline", 158),
            ("isha_kapoor", "credit", "10000.00", "job_milestone_release", milestones["multilingual_storefront_m1"].pk, "Milestone 1 released", 280),
            ("isha_kapoor", "credit", "7000.00", "job_milestone_release", milestones["multilingual_storefront_m2"].pk, "Milestone 2 released", 265),
            ("isha_kapoor", "credit", "5000.00", "job_milestone_release", milestones["multilingual_storefront_m3"].pk, "Final milestone released", 250),
            ("farhan_ali", "credit", "13000.00", "job_milestone_release", milestones["ratelimit_revamp_m1"].pk, "Milestone release before dispute", 192),
            ("siddharth_rao", "credit", "9500.00", "job_milestone_release", milestones["k8s_observability_m1"].pk, "Milestone release for observability setup", 102),
            ("farhan_ali", "debit", "10000.00", "payout_request", 3, "Payout request initiated", 48),
        ]
        for user_key, direction, amount, source_type, reference_id, description, hours_ago in ledger_specs:
            entry = WalletLedger.objects.create(
                user=users[user_key],
                direction=direction,
                amount_inr=Decimal(amount),
                source_type=source_type,
                reference_id=reference_id,
                description=description,
            )
            WalletLedger.objects.filter(pk=entry.pk).update(created_at=now - timedelta(hours=hours_ago))

        payout_specs = [
            ("arjun_verma", "5000.00", "pending", "Weekly freelance payout request", None, None, 40),
            ("isha_kapoor", "8000.00", "approved", "Approved for scheduled payout batch", "ananya_sharma", 24, 30),
            ("farhan_ali", "10000.00", "paid", "Paid via NEFT to registered account", "ananya_sharma", 18, 48),
            ("siddharth_rao", "6000.00", "rejected", "Rejected due to bank account verification mismatch", "ananya_sharma", 16, 22),
        ]
        for user_key, amount, status, note, processed_by_key, processed_hours_ago, created_hours_ago in payout_specs:
            payout = PayoutRequest.objects.create(
                user=users[user_key],
                amount_inr=Decimal(amount),
                status=status,
                note=note,
                processed_by=users.get(processed_by_key) if processed_by_key else None,
                processed_at=(now - timedelta(hours=processed_hours_ago)) if processed_hours_ago else None,
            )
            created_at = now - timedelta(hours=created_hours_ago)
            PayoutRequest.objects.filter(pk=payout.pk).update(
                created_at=created_at,
                updated_at=created_at + timedelta(hours=1),
            )

    def _create_trust_signals(self, jobs, users, now):
        trust_specs = [
            ("isha_kapoor", "job_completed", 5, "Completed multilingual storefront job", "multilingual_storefront", 248),
            ("isha_kapoor", "milestone_released", 2, "Milestone release acknowledged", "multilingual_storefront", 265),
            ("arjun_verma", "milestone_released", 2, "Released ONDC milestone", "ondc_sync", 158),
            ("farhan_ali", "dispute_opened", -2, "Dispute opened on rate-limit revamp", "ratelimit_revamp", 72),
            ("nikhil_banerjee", "job_completed", 3, "Canceled project closed professionally", "bigquery_pipeline", 168),
        ]
        for user_key, signal_type, score_delta, detail, job_key, hours_ago in trust_specs:
            signal = TrustSignal.objects.create(
                user=users[user_key],
                signal_type=signal_type,
                score_delta=score_delta,
                detail=detail,
                related_job=jobs.get(job_key),
            )
            TrustSignal.objects.filter(pk=signal.pk).update(created_at=now - timedelta(hours=hours_ago))

    def _create_notifications(self, users, requests, jobs, request_proposals, disputes, now):
        notification_specs = [
            ("ananya_sharma", 'Your request "DRF validation for GST invoice create API" is in progress.', f"/request/{requests['drf_gst'].pk}/", False, 58),
            ("karan_malhotra", 'Your request "Celery retries for payment status sync are creating duplicates" is in progress.', f"/request/{requests['celery_retry'].pk}/", False, 70),
            ("neha_gupta", 'Your request "Fix flaky pytest suite in CI for notification flows" was resolved.', f"/request/{requests['pytest_flaky'].pk}/", True, 140),
            ("sneha_patil", 'Your request "Dockerize Django + Nginx with health checks for Render" was resolved.', f"/request/{requests['docker_nginx'].pk}/", True, 150),
            ("kavya_reddy", 'Your request "Role-based UI auth in React admin dashboard" was resolved.', f"/request/{requests['rbac_dashboard'].pk}/", False, 118),
            ("tanvi_bansal", 'Your request "Set up Redis caching for product catalog API" was resolved.', f"/request/{requests['redis_cache'].pk}/", False, 116),
            ("pooja_chawla", 'The request "OTP SMS throttle bug causing delayed logins" was canceled.', f"/request/{requests['otp_throttle'].pk}/", True, 94),
            ("siddharth_rao", "Your proposal was selected for a deployment request.", f"/request/{requests['docker_nginx'].pk}/", True, 216),
            ("arjun_verma", "Your proposal was selected for a Celery retry issue.", f"/request/{requests['celery_retry'].pk}/", False, 98),
            ("vivek_iyer", "Your proposal was selected for GST validation task.", f"/request/{requests['drf_gst'].pk}/", False, 94),
            ("rohan_mehta", "Someone accepted your paid job proposal thread.", f"/jobs/{jobs['gst_pdf_service'].pk}/", False, 20),
            ("ananya_sharma", "You have new proposals on your PostgreSQL migration job.", f"/jobs/{jobs['mysql_to_postgres'].pk}/", False, 30),
            ("sneha_patil", "You have proposals waiting on Flutter crash analytics job.", f"/jobs/{jobs['flutter_crashlytics'].pk}/", False, 18),
            ("karan_malhotra", 'Milestone "Delta sync worker + retries" was submitted for review.', f"/jobs/{jobs['ondc_sync'].pk}/", False, 118),
            ("arjun_verma", "INR 12000.00 was released for milestone work.", f"/jobs/{jobs['ondc_sync'].pk}/", True, 158),
            ("isha_kapoor", "Your storefront localization job is marked completed.", f"/jobs/{jobs['multilingual_storefront'].pk}/", True, 248),
            ("devansh_jain", "A dispute was opened on your rate-limit revamp job.", f"/jobs/{jobs['ratelimit_revamp'].pk}/", False, 72),
            ("farhan_ali", "Client opened a dispute on rate-limit revamp job.", f"/jobs/{jobs['ratelimit_revamp'].pk}/", False, 72),
            ("kavya_reddy", "Dispute resolved: escrow refunded for BigQuery pipeline job.", f"/jobs/{jobs['bigquery_pipeline'].pk}/", True, 168),
            ("siddharth_rao", "Milestone pending approval on observability job.", f"/jobs/{jobs['k8s_observability'].pk}/", False, 96),
            ("diya_menon", "New open request matches your saved search: mixed-language search ranking.", f"/request/{requests['search_ranking'].pk}/", False, 8),
            ("rohan_mehta", "New open request matches your saved search: UPI webhook verification.", f"/request/{requests['upi_webhook'].pk}/", False, 6),
        ]
        for user_key, message, link, is_read, hours_ago in notification_specs:
            notif = Notification.objects.create(
                user=users[user_key],
                message=message,
                link=link,
                is_read=is_read,
            )
            Notification.objects.filter(pk=notif.pk).update(created_at=now - timedelta(hours=hours_ago))

        for proposal in request_proposals[:3]:
            notif = Notification.objects.create(
                user=proposal.request.user,
                message=f'New proposal from {proposal.applicant.username} on "{proposal.request.title}".',
                link=f"/request/{proposal.request.pk}/",
                is_read=False,
            )
            Notification.objects.filter(pk=notif.pk).update(created_at=now - timedelta(hours=4))

        return Notification.objects.count()

    def _create_workspaces_and_projects(self, users, skills, now):
        usernames = list(users.keys())
        workspace_specs = [
            {
                "key": "bharatscale_payments",
                "name": "BharatScale Payments Guild",
                "owner": "karan_malhotra",
                "description": "Cross-city engineering team scaling UPI, GST invoicing, and payout reliability.",
                "wallet_inr": Decimal("250000.00"),
                "members": usernames[:12],
            },
            {
                "key": "udaan_commerce_core",
                "name": "Udaan Commerce Core",
                "owner": "ananya_sharma",
                "description": "Marketplace backend and customer experience squad for D2C storefront operations.",
                "wallet_inr": Decimal("185000.00"),
                "members": usernames[6:18],
            },
            {
                "key": "namma_reliability_lab",
                "name": "Namma Reliability Lab",
                "owner": "siddharth_rao",
                "description": "SRE and platform resilience team handling deployments, alerting, and observability.",
                "wallet_inr": Decimal("165000.00"),
                "members": usernames[12:] + usernames[:3],
            },
            {
                "key": "dilli_product_studio",
                "name": "Dilli Product Studio",
                "owner": "kavya_reddy",
                "description": "Product and UI team iterating on growth funnels, search UX, and experimentation.",
                "wallet_inr": Decimal("142000.00"),
                "members": usernames[3:15],
            },
        ]

        workspaces = {}
        for idx, spec in enumerate(workspace_specs, start=1):
            workspace = Workspace.objects.create(
                name=spec["name"],
                owner=users[spec["owner"]],
                description=spec["description"],
                wallet_inr=spec["wallet_inr"],
            )
            Workspace.objects.filter(pk=workspace.pk).update(
                created_at=now - timedelta(days=35 - (idx * 3)),
                updated_at=now - timedelta(days=1 + idx),
            )

            role_cycle = ["admin", "member", "member", "member", "admin", "member"]
            membership_usernames = list(dict.fromkeys([spec["owner"]] + spec["members"]))
            for member_idx, username in enumerate(membership_usernames):
                role = "owner" if username == spec["owner"] else role_cycle[member_idx % len(role_cycle)]
                membership = WorkspaceMembership.objects.create(
                    workspace=workspace,
                    user=users[username],
                    role=role,
                )
                WorkspaceMembership.objects.filter(pk=membership.pk).update(
                    joined_at=now - timedelta(days=30 - member_idx),
                )

            wallet_specs = [
                ("credit", Decimal("40000.00"), "initial_funding", "Seed capital for sprint execution", 26),
                ("debit", Decimal("12000.00"), "tooling_subscription", "Shared infra/tooling bills", 18),
                ("credit", Decimal("8500.00"), "client_recharge", "Client top-up for urgent release", 8),
            ]
            for direction, amount, source_type, note, days_ago in wallet_specs:
                entry = WorkspaceWalletEntry.objects.create(
                    workspace=workspace,
                    actor=users[spec["owner"]],
                    direction=direction,
                    amount_inr=amount,
                    source_type=source_type,
                    note=note,
                )
                WorkspaceWalletEntry.objects.filter(pk=entry.pk).update(
                    created_at=now - timedelta(days=days_ago),
                )
            workspaces[spec["key"]] = workspace

        project_specs = [
            ("bharatscale_payments", "PAYOPS", "Payment Operations", "UPI reconciliation, payouts, and merchant ledger integrity."),
            ("bharatscale_payments", "RISK", "Risk & Compliance", "Fraud prevention, AML checks, and abuse controls."),
            ("udaan_commerce_core", "CATALOG", "Catalog Platform", "Search relevance, catalog cache, and indexing pipelines."),
            ("udaan_commerce_core", "CHECKOUT", "Checkout Experience", "Conversion funnel, taxes, and payment orchestration."),
            ("namma_reliability_lab", "SRE", "Reliability Engineering", "SLA monitoring, incident response, and rollback controls."),
            ("namma_reliability_lab", "OBS", "Observability Stack", "Logs, traces, metrics, and alert precision."),
            ("dilli_product_studio", "GROWTH", "Growth Experiments", "Activation funnels, onboarding, and A/B experimentation."),
            ("dilli_product_studio", "UX", "Design System", "UI consistency, accessibility, and responsive quality."),
        ]

        projects = {}
        for idx, (workspace_key, project_key, name, description) in enumerate(project_specs, start=1):
            project = WorkspaceProject.objects.create(
                workspace=workspaces[workspace_key],
                name=name,
                key=project_key,
                description=description,
                is_active=True,
                created_by=workspaces[workspace_key].owner,
            )
            WorkspaceProject.objects.filter(pk=project.pk).update(
                created_at=now - timedelta(days=28 - idx),
                updated_at=now - timedelta(days=2),
            )
            projects[f"{workspace_key}_{project_key.lower()}"] = project

        issue_templates = [
            ("UPI reconciliation lag on weekend peak traffic", "Bank callback delays are causing temporary mismatch in merchant balances.", "todo", "high", 5),
            ("Railway deploy rollback playbook gaps", "Recent rollout lacked deterministic rollback steps across API and worker dynos.", "in_progress", "critical", 8),
            ("GST credit note edge case in export flow", "Reverse-charge credit notes fail when state and GSTIN metadata are mixed.", "blocked", "medium", 3),
            ("Webhook idempotency audit trail coverage", "Need stronger evidence logs for duplicate webhook payload handling.", "done", "medium", 5),
            ("Dashboard filter persistence bug", "Date and city filters reset on pagination in analytics dashboard.", "todo", "low", 2),
            ("Payout retry dedupe in worker queue", "Duplicate payout retries must be collapsed with a strict dedupe key.", "done", "high", 8),
        ]

        issues = []
        for project_idx, project in enumerate(projects.values(), start=1):
            members = list(
                WorkspaceMembership.objects.filter(workspace=project.workspace)
                .select_related("user")
                .order_by("joined_at")
            )
            if not members:
                continue

            for issue_idx, (title, description, status, priority, points) in enumerate(issue_templates, start=1):
                reporter = members[(issue_idx - 1) % len(members)].user
                assignee = members[(issue_idx + 1) % len(members)].user
                issue = WorkspaceIssue.objects.create(
                    project=project,
                    title=title,
                    description=description,
                    status=status,
                    priority=priority,
                    reporter=reporter,
                    assignee=assignee,
                    estimate_points=points,
                    due_date=(now + timedelta(days=6 + issue_idx)).date(),
                )

                created_at = now - timedelta(days=22 - project_idx, hours=issue_idx * 2)
                updated_at = created_at + timedelta(hours=14 + issue_idx)
                resolved_at = updated_at if status == "done" else None
                WorkspaceIssue.objects.filter(pk=issue.pk).update(
                    created_at=created_at,
                    updated_at=updated_at,
                    resolved_at=resolved_at,
                )
                issue.refresh_from_db()

                activity = WorkspaceIssueActivity.objects.create(
                    issue=issue,
                    actor=reporter,
                    action="created",
                    to_value=status,
                    note="Issue created from sprint planning session.",
                )
                WorkspaceIssueActivity.objects.filter(pk=activity.pk).update(
                    created_at=created_at + timedelta(minutes=10),
                )
                issues.append(issue)

        return workspaces, projects, issues

    def _create_sprints(self, workspaces, projects, users, now):
        sprint_map = {}
        for project in projects.values():
            completed = WorkspaceSprint.objects.create(
                project=project,
                name="Sprint Jan",
                goal="Stabilize critical workflows and close carry-forward bugs.",
                start_date=(now - timedelta(days=55)).date(),
                end_date=(now - timedelta(days=41)).date(),
                status="completed",
                created_by=project.created_by,
            )
            active = WorkspaceSprint.objects.create(
                project=project,
                name="Sprint Feb",
                goal="Improve reliability and ship stakeholder-visible wins.",
                start_date=(now - timedelta(days=8)).date(),
                end_date=(now + timedelta(days=6)).date(),
                status="active",
                created_by=project.created_by,
            )
            planned = WorkspaceSprint.objects.create(
                project=project,
                name="Sprint Mar",
                goal="Prepare expansion roadmap and automation upgrades.",
                start_date=(now + timedelta(days=7)).date(),
                end_date=(now + timedelta(days=21)).date(),
                status="planned",
                created_by=project.created_by,
            )
            WorkspaceSprint.objects.filter(pk=completed.pk).update(created_at=now - timedelta(days=58))
            WorkspaceSprint.objects.filter(pk=active.pk).update(created_at=now - timedelta(days=10))
            WorkspaceSprint.objects.filter(pk=planned.pk).update(created_at=now - timedelta(days=1))
            sprint_map[project.pk] = {"completed": completed, "active": active, "planned": planned}
        return sprint_map

    def _attach_issues_to_sprints(self, issues, sprints, now):
        for issue in issues:
            sprint_set = sprints.get(issue.project_id)
            if not sprint_set:
                continue

            if issue.status == "done":
                issue.sprint = sprint_set["completed"]
            elif issue.status in {"in_progress", "blocked"}:
                issue.sprint = sprint_set["active"]
            else:
                issue.sprint = sprint_set["planned"] if issue.issue_number % 2 == 0 else None
            issue.save(update_fields=["sprint", "resolved_at", "updated_at"])

    def _create_issue_comments_and_activity(self, issues, users, now):
        comment_snippets = [
            "Can we lock scope for this by tomorrow EOD?",
            "Added repro steps from staging logs and linked the failing endpoint traces.",
            "Verified on sandbox tenant; production behavior still needs confirmation.",
            "Let's keep this backward compatible with existing merchant onboarding flow.",
            "Pushed a patch branch and requested review from reliability team.",
        ]

        for idx, issue in enumerate(issues, start=1):
            commenters = [issue.reporter, issue.assignee]
            workspace_members = list(
                WorkspaceMembership.objects.filter(workspace=issue.project.workspace)
                .select_related("user")
                .order_by("joined_at")
            )
            if workspace_members:
                commenters.append(workspace_members[idx % len(workspace_members)].user)

            for comment_idx, commenter in enumerate(commenters[:3], start=1):
                comment = WorkspaceIssueComment.objects.create(
                    issue=issue,
                    author=commenter,
                    content=comment_snippets[(idx + comment_idx) % len(comment_snippets)],
                )
                comment_created = issue.created_at + timedelta(hours=comment_idx * 4)
                WorkspaceIssueComment.objects.filter(pk=comment.pk).update(
                    created_at=comment_created,
                    updated_at=comment_created,
                )
                activity = WorkspaceIssueActivity.objects.create(
                    issue=issue,
                    actor=commenter,
                    action="commented",
                    note=comment.content[:180],
                )
                WorkspaceIssueActivity.objects.filter(pk=activity.pk).update(
                    created_at=comment_created + timedelta(minutes=1),
                )

            if issue.status in {"in_progress", "blocked", "done"}:
                status_activity = WorkspaceIssueActivity.objects.create(
                    issue=issue,
                    actor=issue.assignee or issue.reporter,
                    action="status_changed",
                    from_value="todo",
                    to_value=issue.status,
                )
                WorkspaceIssueActivity.objects.filter(pk=status_activity.pk).update(
                    created_at=issue.updated_at - timedelta(hours=3),
                )

            assignee_activity = WorkspaceIssueActivity.objects.create(
                issue=issue,
                actor=issue.reporter,
                action="assignee_changed",
                from_value="",
                to_value=str(issue.assignee_id or ""),
            )
            WorkspaceIssueActivity.objects.filter(pk=assignee_activity.pk).update(
                created_at=issue.created_at + timedelta(hours=1),
            )

    def _create_chat_data(self, users, requests, jobs, workspaces, now):
        for req in requests.values():
            if not req.accepted_by_id:
                continue
            thread = ChatThread.objects.create(
                thread_type="request",
                title=f"Request Chat: {req.title[:72]}",
                help_request=req,
                created_by=req.user,
            )
            ChatThreadParticipant.objects.create(thread=thread, user=req.user, last_read_at=now - timedelta(hours=4))
            ChatThreadParticipant.objects.create(thread=thread, user=req.accepted_by, last_read_at=now - timedelta(hours=2))
            message_pairs = [
                (req.user, "Thanks for picking this up. Sharing context and expected output here."),
                (req.accepted_by, "Got it. I will start with root-cause analysis and share patch draft."),
                (req.user, "Please prioritize production-safe changes; we need rollback clarity too."),
                (req.accepted_by, "Done. I will add tests and deployment notes before marking complete."),
            ]
            for idx, (sender, text) in enumerate(message_pairs, start=1):
                msg = ChatMessage.objects.create(thread=thread, sender=sender, content=text)
                created_at = now - timedelta(hours=30 - idx)
                ChatMessage.objects.filter(pk=msg.pk).update(created_at=created_at)
            thread.last_message_at = now - timedelta(hours=26)
            thread.save(update_fields=["last_message_at", "updated_at"])

        for job in jobs.values():
            if not job.freelancer_id:
                continue
            thread = ChatThread.objects.create(
                thread_type="job",
                title=f"Job Chat: {job.title[:72]}",
                job=job,
                created_by=job.client,
            )
            ChatThreadParticipant.objects.create(thread=thread, user=job.client, last_read_at=now - timedelta(hours=3))
            ChatThreadParticipant.objects.create(thread=thread, user=job.freelancer, last_read_at=now - timedelta(hours=2))
            message_pairs = [
                (job.client, "Please share milestone-wise delivery evidence before release."),
                (job.freelancer, "Sure. I am uploading proof and changelog for each milestone."),
                (job.client, "Great. Also add rollback notes for infra-impacting changes."),
                (job.freelancer, "Will include rollback notes and post-deploy checks."),
            ]
            for idx, (sender, text) in enumerate(message_pairs, start=1):
                msg = ChatMessage.objects.create(thread=thread, sender=sender, content=text)
                created_at = now - timedelta(hours=22 - idx)
                ChatMessage.objects.filter(pk=msg.pk).update(created_at=created_at)
            thread.last_message_at = now - timedelta(hours=18)
            thread.save(update_fields=["last_message_at", "updated_at"])

        workspace_messages = [
            "Daily standup: please update blockers before 10:30 AM IST.",
            "Production watch: monitor payment retries and alert if error rate crosses threshold.",
            "Design review at 4 PM for dashboard filters and accessibility fixes.",
            "Reminder: close sprint carry-forward tasks before Friday evening.",
            "Please attach deployment notes in issue comments for audit readiness.",
        ]
        for workspace in workspaces.values():
            memberships = list(
                WorkspaceMembership.objects.filter(workspace=workspace)
                .select_related("user")
                .order_by("joined_at")
            )
            if not memberships:
                continue
            thread = ChatThread.objects.create(
                thread_type="workspace",
                title=f"Workspace Room: {workspace.name}",
                workspace=workspace,
                created_by=workspace.owner,
            )
            for item in memberships:
                ChatThreadParticipant.objects.create(
                    thread=thread,
                    user=item.user,
                    last_read_at=now - timedelta(hours=1),
                )

            message_counter = 0
            for round_idx in range(2):
                for member_idx, item in enumerate(memberships):
                    text = workspace_messages[(member_idx + round_idx) % len(workspace_messages)]
                    msg = ChatMessage.objects.create(thread=thread, sender=item.user, content=text)
                    created_at = now - timedelta(hours=max(1, 48 - message_counter))
                    ChatMessage.objects.filter(pk=msg.pk).update(created_at=created_at)
                    message_counter += 1
                    if message_counter >= 28:
                        break
                if message_counter >= 28:
                    break

            thread.last_message_at = now - timedelta(hours=1)
            thread.save(update_fields=["last_message_at", "updated_at"])

    def _create_portfolio_data(self, users, skills, now):
        for idx, user in enumerate(users.values(), start=1):
            user_skills = list(user.skills.all())
            primary_skill = user_skills[0] if user_skills else skills["Python"]
            secondary_skill = user_skills[1] if len(user_skills) > 1 else primary_skill
            entries = [
                (
                    f"{primary_skill.name} Reliability Upgrade for Indian Fintech API",
                    "Reduced incident volume with observability and deterministic rollback safeguards.",
                    "https://example.in/case-study/reliability",
                    "https://github.com/example/reliability-playbook",
                    primary_skill,
                    True,
                ),
                (
                    f"{secondary_skill.name} Feature Delivery for Multi-city Commerce Team",
                    "Delivered measurable conversion improvement with maintainable architecture changes.",
                    "https://example.in/case-study/feature-delivery",
                    "https://github.com/example/feature-delivery",
                    secondary_skill,
                    False,
                ),
            ]
            for entry_idx, (title, summary, project_url, evidence_url, skill, is_featured) in enumerate(entries, start=1):
                item = PortfolioItem.objects.create(
                    user=user,
                    title=title,
                    summary=summary,
                    project_url=project_url,
                    evidence_url=evidence_url,
                    primary_skill=skill,
                    is_featured=is_featured,
                )
                created_at = now - timedelta(days=45 - idx, hours=entry_idx * 3)
                PortfolioItem.objects.filter(pk=item.pk).update(
                    created_at=created_at,
                    updated_at=created_at + timedelta(hours=2),
                )

    def _create_integrations_data(self, users, now):
        active_users = list(users.values())[:14]
        for idx, user in enumerate(active_users, start=1):
            api_key, _ = IntegrationApiKey.create_key(user, f"{user.first_name} Integration Key")
            IntegrationApiKey.objects.filter(pk=api_key.pk).update(
                created_at=now - timedelta(days=18 - idx),
                last_used_at=now - timedelta(days=max(1, idx // 2)),
            )
            if idx % 4 == 0:
                IntegrationApiKey.objects.filter(pk=api_key.pk).update(
                    is_active=False,
                    revoked_at=now - timedelta(days=2),
                )

            endpoint = WebhookEndpoint.objects.create(
                user=user,
                name=f"{user.first_name} Ops Webhook",
                url=f"https://hooks.example.in/{user.username}/events",
                subscribed_events=[
                    "request.status_changed",
                    "job.status_changed",
                    "milestone.released",
                    "workspace.issue_status_changed",
                ],
                is_active=idx % 5 != 0,
            )
            WebhookEndpoint.objects.filter(pk=endpoint.pk).update(created_at=now - timedelta(days=16 - idx))

            delivery_specs = [
                ("workspace.issue_status_changed", 200, True, "Accepted"),
                ("milestone.released", 202, True, "Queued"),
                ("job.status_changed", 500, False, "Remote timeout"),
            ]
            for delivery_idx, (event_type, status_code, succeeded, excerpt) in enumerate(delivery_specs, start=1):
                delivery = WebhookDelivery.objects.create(
                    endpoint=endpoint,
                    event_type=event_type,
                    payload={"username": user.username, "event": event_type, "attempt": delivery_idx},
                    status_code=status_code,
                    response_excerpt=excerpt,
                    succeeded=succeeded,
                )
                WebhookDelivery.objects.filter(pk=delivery.pk).update(
                    created_at=now - timedelta(days=6, hours=(idx + delivery_idx)),
                )

    def _create_moderation_and_fraud_data(self, users, requests, jobs, disputes, now):
        request_values = list(requests.values())
        job_values = list(jobs.values())
        comment_values = list(Comment.objects.all()[:12])
        dispute_values = list(disputes)

        flag_specs = [
            ("ananya_sharma", "request", request_values[0].pk, "Contains potential sensitive merchant info.", "reviewed", "karan_malhotra", "Redacted sensitive fields.", 36),
            ("rohan_mehta", "job", job_values[0].pk, "Scope appears duplicated from earlier listing.", "open", None, "", 18),
            ("priya_nair", "comment", comment_values[0].pk if comment_values else 1, "Comment tone violates collaboration norms.", "dismissed", "karan_malhotra", "No policy violation after context review.", 20),
            ("vivek_iyer", "user", users["harshit_saxena"].pk, "Repeated aggressive behavior in proposal threads.", "actioned", "ananya_sharma", "User warned and temporarily limited.", 30),
            ("devansh_jain", "dispute", dispute_values[0].pk if dispute_values else 1, "Need audit review for disputed milestone evidence.", "open", None, "", 10),
            ("kavya_reddy", "request", request_values[2].pk, "Potential duplicate request from same team.", "reviewed", "ananya_sharma", "Merged with canonical issue thread.", 12),
        ]
        for reporter, target_type, target_id, reason, status, reviewed_by, note, hours_ago in flag_specs:
            flag = ModerationFlag.objects.create(
                reported_by=users[reporter],
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                status=status,
                reviewed_by=users.get(reviewed_by) if reviewed_by else None,
                resolution_note=note,
                resolved_at=(now - timedelta(hours=hours_ago - 2)) if status != "open" else None,
            )
            ModerationFlag.objects.filter(pk=flag.pk).update(created_at=now - timedelta(hours=hours_ago))

        alert_specs = [
            ("farhan_ali", "devansh_jain", "collusion", "high", "Repeated high-value closed-loop job pair in short window.", False, 72),
            ("karan_malhotra", "arjun_verma", "unusual_pattern", "medium", "Milestone release pattern deviates from project baseline.", False, 58),
            ("pooja_chawla", "siddharth_rao", "sla_breach", "low", "SLA reminder threshold crossed before first response.", True, 40),
            ("rohan_mehta", "vivek_iyer", "transfer_velocity", "medium", "KP transfer velocity spike detected in 24-hour window.", False, 32),
            ("ananya_sharma", "nikhil_banerjee", "unusual_pattern", "low", "Unusual query of payout endpoints from new IP range.", True, 24),
        ]
        for user_key, related_key, alert_type, severity, description, resolved, hours_ago in alert_specs:
            alert = FraudAlert.objects.create(
                user=users[user_key],
                related_user=users[related_key],
                alert_type=alert_type,
                severity=severity,
                description=description,
                metadata={"seed": "indian_demo", "source": "risk_engine_v2"},
                is_resolved=resolved,
            )
            created_at = now - timedelta(hours=hours_ago)
            FraudAlert.objects.filter(pk=alert.pk).update(
                created_at=created_at,
                updated_at=created_at + timedelta(hours=3),
            )

    def _create_kp_transfer_data(self, users, now):
        user_list = list(users.values())
        transfer_counter = 0
        for idx, sender in enumerate(user_list):
            first_recipient = user_list[(idx + 3) % len(user_list)]
            second_recipient = user_list[(idx + 7) % len(user_list)]
            for recipient, amount in [(first_recipient, 6 + (idx % 5)), (second_recipient, 8 + (idx % 4))]:
                if sender.pk == recipient.pk:
                    continue
                transfer = KPTransfer.objects.create(
                    sender=sender,
                    recipient=recipient,
                    amount=amount,
                )
                KPTransfer.objects.filter(pk=transfer.pk).update(
                    created_at=now - timedelta(hours=120 - transfer_counter),
                )
                transfer_counter += 1

    def _create_attachment_data(self, users, requests, jobs, issues, now):
        def create_attachment(target, uploader, caption, body, hours_ago, suffix):
            attachment = Attachment.objects.create(
                content_type=ContentType.objects.get_for_model(target.__class__),
                object_id=target.pk,
                uploaded_by=uploader,
                file=ContentFile(body.encode("utf-8"), name=f"{uploader.username}_{suffix}.txt"),
                caption=caption,
            )
            Attachment.objects.filter(pk=attachment.pk).update(
                created_at=now - timedelta(hours=hours_ago),
            )

        request_items = list(requests.values())[:6]
        for idx, req in enumerate(request_items, start=1):
            create_attachment(
                target=req,
                uploader=req.user,
                caption="Error logs and reproduction notes",
                body=f"Request #{req.pk} debug notes from {req.user.username}",
                hours_ago=70 - idx * 2,
                suffix=f"request_{req.pk}",
            )

        job_items = list(jobs.values())[:5]
        for idx, job in enumerate(job_items, start=1):
            create_attachment(
                target=job,
                uploader=job.client,
                caption="Scope brief and sample payloads",
                body=f"Job #{job.pk} scope brief and payload examples.",
                hours_ago=58 - idx * 2,
                suffix=f"job_{job.pk}",
            )

        request_comments = list(Comment.objects.all()[:10])
        for idx, comment in enumerate(request_comments, start=1):
            create_attachment(
                target=comment,
                uploader=comment.user,
                caption="Stack trace snippet",
                body=f"Comment #{comment.pk} stack trace attachment.",
                hours_ago=46 - idx,
                suffix=f"comment_{comment.pk}",
            )

        for idx, issue in enumerate(issues[:10], start=1):
            create_attachment(
                target=issue,
                uploader=issue.reporter,
                caption="Issue context document",
                body=f"Issue {issue.issue_key} context and acceptance criteria.",
                hours_ago=38 - idx,
                suffix=f"issue_{issue.pk}",
            )

    def _create_deliverables_data(self, milestones, users, now):
        for key, milestone in milestones.items():
            if milestone.status not in {"submitted", "released", "disputed"}:
                continue
            submitter = milestone.job.freelancer or milestone.job.client
            deliverable = MilestoneDeliverable.objects.create(
                milestone=milestone,
                submitted_by=submitter,
                proof_text=f"Deliverable evidence for {milestone.title}. Includes logs, screenshots, and test summary.",
                status="submitted",
            )
            if milestone.status == "released":
                deliverable.status = "approved"
                deliverable.approved_at = milestone.released_at or (now - timedelta(hours=24))
                deliverable.save(update_fields=["status", "approved_at", "updated_at"])
            elif milestone.status == "disputed":
                deliverable.status = "revision_requested"
                deliverable.revision_note = "Please provide stronger proof for tenant-specific edge cases."
                deliverable.requested_revision_at = now - timedelta(hours=36)
                deliverable.save(
                    update_fields=["status", "revision_note", "requested_revision_at", "updated_at"],
                )
            MilestoneDeliverable.objects.filter(pk=deliverable.pk).update(
                created_at=now - timedelta(hours=90),
            )

    def _create_experiment_data(self, users, now):
        experiment_specs = [
            {
                "name": "Matching Algorithm v2",
                "slug": "matching-algo-v2",
                "description": "Compare control ranking vs skill-boost opportunity ranking.",
                "traffic": 100,
                "variants": [("control", "Control", 50), ("skill_boost", "Skill Boost", 50)],
            },
            {
                "name": "Compact Navigation Treatment",
                "slug": "compact-nav-treatment",
                "description": "Test reduced top-nav density for faster scanning.",
                "traffic": 80,
                "variants": [("baseline", "Baseline", 60), ("compact", "Compact", 40)],
            },
        ]

        for spec in experiment_specs:
            experiment = Experiment.objects.create(
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
                is_active=True,
                traffic_percentage=spec["traffic"],
                starts_at=now - timedelta(days=20),
                ends_at=now + timedelta(days=20),
            )
            variants = []
            for key, label, weight in spec["variants"]:
                variant = ExperimentVariant.objects.create(
                    experiment=experiment,
                    key=key,
                    label=label,
                    weight=weight,
                )
                variants.append(variant)

            user_list = list(users.values())
            for idx, user in enumerate(user_list):
                assigned_variant = variants[idx % len(variants)]
                assignment = ExperimentAssignment.objects.create(
                    experiment=experiment,
                    variant=assigned_variant,
                    user=user,
                    session_key=f"seed-session-{experiment.slug}-{idx}",
                )
                ExperimentAssignment.objects.filter(pk=assignment.pk).update(
                    created_at=now - timedelta(days=10, hours=idx),
                )

    def _expand_saved_search_activity(self, users, skills, tags, now):
        tag_values = list(tags.values())
        for idx, user in enumerate(users.values(), start=1):
            user_skills = list(user.skills.all())
            primary_skill = user_skills[0] if user_skills else skills["Python"]
            secondary_skill = user_skills[1] if len(user_skills) > 1 else primary_skill
            tag_a = tag_values[idx % len(tag_values)]
            tag_b = tag_values[(idx + 7) % len(tag_values)]

            first_search = SavedSearch.objects.create(
                user=user,
                query=f"{primary_skill.name.lower()} production fixes",
                skill=primary_skill,
                tag=tag_a,
                is_active=True,
                last_notified_at=now - timedelta(hours=14 + idx),
            )
            second_search = SavedSearch.objects.create(
                user=user,
                query=f"{secondary_skill.name.lower()} performance improvements",
                skill=secondary_skill,
                tag=tag_b,
                is_active=idx % 3 != 0,
                last_notified_at=now - timedelta(hours=10 + idx),
            )
            SavedSearch.objects.filter(pk=first_search.pk).update(created_at=now - timedelta(days=5, hours=idx))
            SavedSearch.objects.filter(pk=second_search.pk).update(created_at=now - timedelta(days=3, hours=idx))

            for note_idx, search in enumerate([first_search, second_search], start=1):
                notif = Notification.objects.create(
                    user=user,
                    message=f"{2 + note_idx} new request(s) match your saved search '{search.query[:30]}...'.",
                    link="/saved-searches/",
                    is_read=note_idx % 2 == 0,
                )
                Notification.objects.filter(pk=notif.pk).update(
                    created_at=now - timedelta(hours=6 + idx + note_idx),
                )

    def _write_seed_credentials_file(self, users, password, generated_at, summary):
        lines = []
        lines.append("# Seeded Account Credentials")
        lines.append("")
        lines.append(f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("")
        lines.append("This dataset was reseeded with realistic Indian developer personas and feature-rich activity.")
        lines.append(f"All seeded accounts use the same password: `{password}`")
        lines.append("")
        lines.append("## Quick Demo Accounts")
        lines.append("")
        lines.append("- `ananya_sharma` - Productive poster + operations style account")
        lines.append("- `arjun_verma` - Active helper/freelancer with in-progress milestones")
        lines.append("- `isha_kapoor` - High-rated frontend specialist with completed jobs")
        lines.append("- `farhan_ali` - Redis/API specialist with dispute + payout history")
        lines.append("- `diya_menon` - ML/search user with saved-search activity")
        lines.append("")
        lines.append("## Seed Summary")
        lines.append("")
        lines.append(f"- Users: **{summary['users']}**")
        lines.append(f"- Help Requests: **{summary['help_requests']}**")
        lines.append(f"- Paid Jobs: **{summary['jobs']}**")
        lines.append(f"- Notifications: **{summary['notifications']}**")
        lines.append(f"- Workspaces: **{summary['workspaces']}**")
        lines.append(f"- Workspace Projects: **{summary['projects']}**")
        lines.append(f"- Workspace Issues: **{summary['issues']}**")
        lines.append(f"- Chat Messages: **{summary['chat_messages']}**")
        lines.append(f"- Attachments: **{summary['attachments']}**")
        lines.append("")
        lines.append("| Full Name | Username | Password | Email |")
        lines.append("|---|---|---|---|")

        sorted_users = sorted(users.values(), key=lambda user: user.username)
        for user in sorted_users:
            full_name = f"{user.first_name} {user.last_name}".strip()
            lines.append(f"| {full_name} | `{user.username}` | `{password}` | `{user.email}` |")

        target = settings.BASE_DIR / "SEEDED_CREDENTIALS.md"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
