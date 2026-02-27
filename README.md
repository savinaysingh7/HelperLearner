# HelperLearner

HelperLearner is a Django 6 knowledge marketplace where users post help requests with Knowledge Point (KP) bounties, other users claim and solve them, and KP is transferred safely through escrowed workflows.

## Core Features
- KP escrow and refund lifecycle for request creation, cancellation, deletion, and expiry.
- Private requester/helper comments after claim.
- Ratings for resolved requests.
- Notification system for request lifecycle events (in-app + email).
- Per-user notification delivery preferences (`in-app`, `email`, `both`, `none`).
- User skill profiles, leaderboard, and personal dashboard analytics.
- Tag-based discovery, skill/tag browsing, and filtered request browsing.
- Unified full-text search across requests/users/skills with highlighting.
- Personalized user activity feed and KP claim/transfer actions.
- Saved searches with notification automation for new matching requests.
- AI draft assistant for request posting/editing (Gemini-powered title/description/tag/skill suggestions).
- Trust score metrics surfaced on profiles, leaderboard, and user API.
- Dual marketplace model: KP help requests + INR paid freelance jobs.
- Proposal-first hiring flow for both KP requests and paid INR jobs.
- Side-by-side proposal comparison pages with bid, ETA, rating, and completion metrics.
- Freelancer proposal milestones that auto-convert to real job milestones on selection.
- Deliverables + revision workflow for milestones (proof upload, revision requests, approvals).
- Milestone-based INR escrow release, disputes, wallet ledger, and payout requests.
- SLA engine for response reminders and optional milestone auto-release.
- Visual lifecycle timelines on request/job detail pages for escrow state transparency.
- User-selectable UI density mode (`comfortable` or `compact`) persisted in profile settings.
- Trust Score v2 breakdown (on-time %, dispute %, response time, streak).
- Risk/fraud checks for collusion and KP transfer velocity/patterns.
- Team workspaces with shared wallet and role permissions.
- Jira-style workspace project boards with issue tracking, transitions, and activity logs.
- Realtime chat inbox with request/job/workspace conversation rooms.
- Generic attachment uploads for requests, jobs, and comments.
- API keys + webhook delivery logs for external integrations.
- Moderation console with report queue, fraud alerts, and account suspension actions.
- PWA support (manifest + service worker) and realtime websocket notification hooks.
- Advanced analytics dashboard and lightweight A/B experimentation framework.
- CSV export for wallet ledger and personal dispute history.
- DRF read-only API with pagination, filtering, and grouped search.
- Custom Django admin dashboards/actions for all models.

## Local Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost
   ```
4. Run database migrations:
   ```bash
   python manage.py migrate
   ```
5. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Email Setup
Development uses console email output:
- `EMAIL_BACKEND = django.core.mail.backends.console.EmailBackend`

Production reads SMTP settings from environment variables:
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS` (optional, defaults to `True`)
- `DEFAULT_FROM_EMAIL` (optional, defaults to `no-reply@helperlearner.local`)

## AI Assistant Setup (Gemini)
Set the following environment variables:
- `GEMINI_API_KEY`
- `GEMINI_MODEL` (optional, defaults to `gemini-flash-latest`)

The request form includes an **Improve with AI** action that calls:
- `POST /post/assist/`

## Production Configuration
Use `helperlearner_root.settings.prod` with explicit secure environment variables.

Required:
- `DATABASE_URL`
- `SECRET_KEY` (must be long/random: minimum 50 chars, high entropy)
- `ALLOWED_HOSTS` (comma-separated hostnames; wildcard `*` is rejected)

Notes:
- `DEBUG` is always `False` in production settings.
- `SECURE_PROXY_SSL_HEADER` is enabled for reverse-proxy deployments.

### Optional Redis Cache
If Redis is available, set:
- `REDIS_URL` (example: `redis://localhost:6379/1`)

The app auto-switches to `django-redis` when installed; otherwise it falls back to local-memory cache.

### Optional Sentry Error Monitoring
Set:
- `SENTRY_DSN`
- `SENTRY_ENVIRONMENT` (optional)
- `SENTRY_TRACES_SAMPLE_RATE` (optional, default `0.0`)
- `SENTRY_PROFILES_SAMPLE_RATE` (optional, default `0.0`)

If `sentry-sdk` is installed and `SENTRY_DSN` is set, Sentry is initialized automatically.

### Optional Celery Worker + Beat
Set:
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `READINESS_CHECK_CELERY` (optional, default `False`; when `True`, `/readyz/` verifies broker reachability)
- `READINESS_CHECK_CELERY_TIMEOUT_SECONDS` (optional, default `2`)

Background schedules are configured for:
- request expiry
- saved-search notifications
- SLA engine checks

Run worker:
```bash
celery -A helperlearner_root.celery:celery_app worker -l info
```

Run beat scheduler:
```bash
celery -A helperlearner_root.celery:celery_app beat -l info
```

## Request Expiry Command
Expire overdue open requests (cancel + refund + notify):
```bash
python manage.py expire_requests
```

### Scheduling Note (Cron / Railway Cron)
You can run this command on a schedule (for example every hour) with cron or Railway cron jobs.

Example cron entry:
```cron
0 * * * * /path/to/venv/bin/python /path/to/project/manage.py expire_requests
```

On Railway, configure a cron service that runs:
```bash
python manage.py expire_requests
```

This command now also sends expiry notification emails to request posters.

## Saved Search Notification Command
Notify users about newly created open requests that match active saved searches:
```bash
python manage.py notify_saved_searches
```

## SLA Engine Command
Run SLA reminders and milestone auto-release rules:
```bash
python manage.py run_sla_engine
```

## Web Endpoints
- `GET /healthz/` lightweight health check endpoint for uptime probes
- `GET /readyz/` readiness probe (database + cache checks, optional Celery broker check)
- `GET /search/?q=` unified search page for requests/users/skills
- `GET /feed/` personalized activity feed (login required)
- `GET /chat/` unified chat inbox for all conversation threads (login required)
- `GET,POST /chat/thread/<id>/` view and send messages in a thread (login required, supports async send + `?after_id=` polling)
- `GET,POST /saved-searches/` create/manage saved request filters
- `GET /recommendations/` personalized ranked opportunities
- `GET,POST /workspaces/` create and browse team workspaces
- `GET /workspaces/<slug>/` workspace members + shared wallet ledger
- `GET /workspaces/<slug>/chat/` workspace group chat room
- `GET,POST /workspaces/<slug>/projects/` workspace project list + create board (owner/admin create)
- `GET /workspaces/<slug>/projects/<project_id>/` Kanban board for a workspace project
- `GET,POST /workspaces/<slug>/projects/<project_id>/issues/new/` create issue
- `GET,POST /workspaces/<slug>/projects/<project_id>/issues/<issue_id>/` issue detail + activity timeline + comments
- `GET,POST /workspaces/<slug>/projects/<project_id>/issues/<issue_id>/edit/` edit issue
- `POST /workspaces/<slug>/projects/<project_id>/issues/<issue_id>/transition/` move issue status lane
- `POST /workspaces/<slug>/projects/<project_id>/sprints/create/` create sprint window
- `POST /workspaces/<slug>/projects/<project_id>/sprints/<sprint_id>/start/` activate sprint
- `POST /workspaces/<slug>/projects/<project_id>/sprints/<sprint_id>/complete/` complete sprint
- `GET,POST /kp/claim-daily/` daily +10 KP claim (24-hour cooldown)
- `GET,POST /kp/transfer/` confirmed KP transfer flow
- `GET,POST /accounts/profile/edit/` includes notification preference management
- `GET,POST /portfolio/` manage public helper portfolio
- `GET,POST /integrations/` API key + webhook management
- `GET /moderation/` moderation queue (staff)
- `GET /analytics/advanced/` analytics dashboard (staff)
- `POST /post/assist/` AI draft improvement endpoint (login + CSRF required)
- `GET /jobs/` paid freelance jobs discovery
- `GET,POST /jobs/post/` create paid freelance job and fund escrow
- `GET /jobs/<id>/` paid job detail with milestones
- `GET /jobs/<id>/chat/` open paid-job participant chat
- `GET /jobs/<id>/proposals/compare/` side-by-side proposal comparison
- `GET /request/<id>/proposals/compare/` side-by-side proposal comparison
- `POST /request/<id>/propose/` submit or update helper proposal
- `GET /request/<id>/chat/` open request participant chat
- `POST /request/<id>/proposals/<proposal_id>/select/` select a helper proposal
- `POST /request/<id>/proposals/withdraw/` withdraw own helper proposal
- `POST /jobs/<id>/propose/` submit or update freelancer proposal
- `POST /jobs/<id>/proposals/<proposal_id>/select/` select a freelancer proposal
- `POST /jobs/<id>/proposals/withdraw/` withdraw own freelancer proposal
- `POST /jobs/<id>/claim/` accept paid job as freelancer
- `POST /jobs/<id>/milestones/add/` add milestone (client)
- `POST /jobs/<id>/milestones/<mid>/submit/` submit milestone (freelancer)
- `POST /jobs/<id>/milestones/<mid>/deliverable/` submit proof deliverable
- `POST /jobs/<id>/milestones/<mid>/revision/` request milestone changes (client)
- `POST /jobs/<id>/milestones/<mid>/approve/` approve deliverable before release
- `POST /jobs/<id>/milestones/<mid>/release/` release milestone payment (client)
- `GET,POST /jobs/<id>/cancel/` cancel paid job and refund escrow
- `POST /jobs/<id>/dispute/` open paid-job dispute
- `GET,POST /wallet/` INR wallet and payout request page
- `GET /wallet/export/` export wallet ledger as CSV
- `GET /jobs/disputes/export/` export your job disputes as CSV

## API Endpoints
All endpoints are paginated (`page_size=10`).

- `GET /api/requests/` (filters: `status`, `skill`)
- `GET /api/requests/<id>/`
- `GET /api/requests/<id>/comments/` (public comments only)
- `GET /api/jobs/` (filters: `status`, `skill`, `payment_type`)
- `GET /api/users/` (username, avg_rating, trust_score, knowledge_points, skills)
- `GET /api/skills/` (skill + request_count)
- `GET /api/workspace-projects/` (authenticated; member-scoped projects with issue counters)
- `GET /api/workspace-issues/` (authenticated; filters: `project`, `workspace`, `status`, `priority`, `assignee`, `sprint`)
- `GET /api/workspace-issues/<id>/comments/` (authenticated; issue comments for member-visible issues)
- `GET /api/search/?q=` (grouped `requests`, `users`, `skills`)

Realtime websocket endpoint (when Channels is installed):
- `GET ws://<host>/ws/updates/`

## Testing
Run the full test suite:
```bash
python manage.py test
```

## Demo Seeding
Replace demo/seeded data with realistic Indian marketplace activity:
```bash
python manage.py seed_indian_demo_data
```

Optional:
```bash
python manage.py seed_indian_demo_data --password "YourDemoPass123!"
python manage.py seed_indian_demo_data --drop-superusers
```

## Product Roadmap Ideas
- Full dispute arbitration console with admin evidence review and escrow split rules.
- KYC workflow and payout processor integration for real INR withdrawals.
- Anti-collusion and fraud-scoring engine with auto-flag thresholds.
- Saved-search digests with per-query frequency options (instant/daily/weekly).
- SLA-backed paid jobs with automatic penalties for breaches.
- API keys for third-party integrations and usage limits.

## Operations Runbook (Practical)
1. Startup checks:
   - `python manage.py check`
   - `python manage.py migrate --plan`
   - `python manage.py test`
2. Runtime checks:
   - hit `/healthz/` for liveness
   - hit `/readyz/` for DB/cache readiness (and broker readiness when `READINESS_CHECK_CELERY=True`)
3. Scheduled workflows:
   - run Celery worker + beat or cron equivalents for `expire_requests`, `notify_saved_searches`, `run_sla_engine`
4. Incident baseline:
   - use `X-Request-ID` from responses/logs for traceability
   - inspect `server_log.txt` and Sentry events for stack traces
5. Rollback safety:
   - maintain DB backups before deploy
   - revert app release and run forward-only migration strategy
