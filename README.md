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

## Web Endpoints
- `GET /search/?q=` unified search page for requests/users/skills
- `GET /feed/` personalized activity feed (login required)
- `GET,POST /kp/claim-daily/` daily +10 KP claim (24-hour cooldown)
- `GET,POST /kp/transfer/` confirmed KP transfer flow

## API Endpoints
All endpoints are paginated (`page_size=10`).

- `GET /api/requests/` (filters: `status`, `skill`)
- `GET /api/requests/<id>/`
- `GET /api/requests/<id>/comments/` (public comments only)
- `GET /api/users/` (username, avg_rating, knowledge_points, skills)
- `GET /api/skills/` (skill + request_count)
- `GET /api/search/?q=` (grouped `requests`, `users`, `skills`)

## Testing
Run the full test suite:
```bash
python manage.py test
```
