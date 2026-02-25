# HelperLearner

HelperLearner is a Django 6 knowledge marketplace where users post help requests with Knowledge Point (KP) bounties, other users claim and solve them, and KP is transferred safely through escrowed workflows.

## Core Features
- KP escrow and refund lifecycle for request creation, cancellation, deletion, and expiry.
- Private requester/helper comments after claim.
- Ratings for resolved requests.
- Notification system for request lifecycle events.
- User skill profiles, leaderboard, and personal dashboard analytics.
- Tag-based discovery, skill/tag browsing, and filtered request browsing.
- DRF read-only API with pagination and filtering.

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

## API Endpoints
All endpoints are paginated (`page_size=10`).

- `GET /api/requests/` (filters: `status`, `skill`)
- `GET /api/requests/<id>/`
- `GET /api/requests/<id>/comments/` (public comments only)
- `GET /api/users/` (username, avg_rating, knowledge_points, skills)
- `GET /api/skills/` (skill + request_count)

## Testing
Run the full test suite:
```bash
python manage.py test
```
