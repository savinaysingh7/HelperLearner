# HelperLearner

HelperLearner is a Django 6 knowledge marketplace where users post help requests with Knowledge Point (KP) bounties, other users claim and solve them, and KP is transferred safely through escrowed workflows.

## Core Features
- KP escrow and refund lifecycle for request creation, cancellation, deletion, and expiry.
- Private requester/helper comments after claim.
- Ratings for resolved requests.
- Notification system for request lifecycle events (in-app + email).
- User skill profiles, leaderboard, and personal dashboard analytics.
- Tag-based discovery, skill/tag browsing, and filtered request browsing.
- Unified full-text search across requests/users/skills with highlighting.
- Personalized user activity feed and KP claim/transfer actions.
- Saved searches with notification automation for new matching requests.
- Trust score metrics surfaced on profiles, leaderboard, and user API.
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

## Production Configuration
Use `helperlearner_root.settings.prod` with explicit secure environment variables.

Required:
- `DATABASE_URL`
- `SECRET_KEY` (must be long/random: minimum 50 chars, high entropy)
- `ALLOWED_HOSTS` (comma-separated hostnames; wildcard `*` is rejected)

Notes:
- `DEBUG` is always `False` in production settings.
- `SECURE_PROXY_SSL_HEADER` is enabled for reverse-proxy deployments.

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

## Web Endpoints
- `GET /search/?q=` unified search page for requests/users/skills
- `GET /feed/` personalized activity feed (login required)
- `GET,POST /saved-searches/` create/manage saved request filters
- `GET,POST /kp/claim-daily/` daily +10 KP claim (24-hour cooldown)
- `GET,POST /kp/transfer/` confirmed KP transfer flow

## API Endpoints
All endpoints are paginated (`page_size=10`).

- `GET /api/requests/` (filters: `status`, `skill`)
- `GET /api/requests/<id>/`
- `GET /api/requests/<id>/comments/` (public comments only)
- `GET /api/users/` (username, avg_rating, trust_score, knowledge_points, skills)
- `GET /api/skills/` (skill + request_count)
- `GET /api/search/?q=` (grouped `requests`, `users`, `skills`)

## Testing
Run the full test suite:
```bash
python manage.py test
```

## Product Roadmap Ideas
- Dispute workflow for resolved requests (admin-reviewed partial or full refund paths).
- Moderation/report queue for requests/comments/profiles with admin actions and history.
- File/snippet attachments with type and size controls.
- Saved-search email digests and per-user notification preferences.
- Milestone-based request payouts with staged KP release.
- API keys for third-party integrations and usage limits.
