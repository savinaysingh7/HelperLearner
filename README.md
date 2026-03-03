# HelperLearner

> **Solve coding blockers, earn KP, and help teammates ship.**

HelperLearner is a full-stack **developer knowledge marketplace** built with Django 6 where developers post coding problems with Knowledge Point (KP) bounties, claim and resolve them, take on freelance jobs with real INR payments via Razorpay, and collaborate in workspaces — all secured by an escrow system, trust scores, and AI-powered features.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Django](https://img.shields.io/badge/Django-6.0-green?logo=django)
![License](https://img.shields.io/badge/License-MIT-yellow)
![CI](https://img.shields.io/github/actions/workflow/status/savinaysingh7/HelperLearner/ci.yml?label=CI)

---

## ✨ Features

### Core Marketplace
| Feature | Description |
|---------|-------------|
| **Help Requests** | Post coding problems with KP bounties. Helpers claim, resolve, and earn KP. |
| **Freelance Jobs** | Post paid jobs (INR). Milestone-based workflow with escrow payments. |
| **Razorpay Payments** | Real payment gateway for wallet top-ups and milestone funding. |
| **Escrow System** | Client funds are held in escrow until milestones are approved. |
| **KP Economy** | Knowledge Points as internal currency. Earn by helping, spend by asking. |
| **Full-Text Search** | PostgreSQL `SearchVector`/`SearchRank` for relevance-ranked results. |

### Collaboration
| Feature | Description |
|---------|-------------|
| **Real-Time Chat** | WebSocket-powered chat threads for requests, jobs, and workspaces. |
| **Workspaces** | Team spaces with boards, sprints, and issues (mini-Jira). |
| **Sprint Burndown** | Charts showing daily progress toward sprint completion. |
| **Activity Feed** | Real-time feed of platform activity with WebSocket push. |

### AI & Intelligence
| Feature | Description |
|---------|-------------|
| **AI Assistant** | Gemini-powered request assistance and auto-summaries. |
| **Helper Matching** | AI-scored recommendations based on skills, ratings, and trust. |
| **Content Moderation** | Pattern detection + optional Gemini classification (safe/flagged/blocked). |
| **Smart Recommendations** | Personalized request suggestions based on user skills. |

### Trust & Security
| Feature | Description |
|---------|-------------|
| **Trust Scores** | Multi-signal trust scoring (ratings, proposals, disputes, tenure). |
| **Fraud Detection** | Risk engine with configurable alerts and thresholds. |
| **API Security** | HMAC-signed webhooks, hashed API keys, CSRF, brute-force lockout. |
| **GDPR Export** | One-click data export as JSON ZIP. Rate-limited to 1/24h. |
| **Content Flags** | Community reporting + admin moderation console. |

### DevOps
| Feature | Description |
|---------|-------------|
| **Docker** | Full `docker-compose` stack (Django + PostgreSQL + Redis + Celery). |
| **CI/CD** | GitHub Actions with PostgreSQL service, deploy checks, and linting. |
| **Celery Workers** | Background tasks: email sending, request expiry, SLA reminders. |
| **API Throttling** | DRF rate limiting (100/day anon, 1000/day authenticated). |
| **Sentry** | Error tracking and performance monitoring. |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 16 (or SQLite for dev)
- Redis (optional, for Celery/WebSockets)

### Local Setup

```bash
# Clone
git clone https://github.com/savinaysingh7/HelperLearner.git
cd HelperLearner

# Virtual environment
python -m venv venv
source venv/bin/activate      # Linux/Mac
.\venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# Edit .env with your settings

# Database
python manage.py migrate

# Run
python manage.py runserver
```

### Docker

```bash
docker-compose up --build
# Access at http://localhost:8000
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `DEBUG` | No | `True` for development (default: `False`) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | No | Google Gemini API key for AI features |
| `RAZORPAY_KEY_ID` | No | Razorpay key for payments |
| `RAZORPAY_KEY_SECRET` | No | Razorpay secret for payments |
| `RAZORPAY_WEBHOOK_SECRET` | No | Razorpay webhook signing secret |
| `CELERY_BROKER_URL` | No | Redis URL for Celery (default: redis://localhost:6379/0) |
| `SENTRY_DSN` | No | Sentry error tracking DSN |
| `SITE_URL` | No | Base URL for email links |

---

## 📡 API Reference

### REST Endpoints (JSON)

All API endpoints are under `/api/` and require session or API key authentication.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/requests/` | List help requests (paginated) |
| `POST` | `/api/requests/` | Create a help request |
| `GET` | `/api/requests/{id}/` | Get request detail |
| `GET` | `/api/jobs/` | List freelance jobs |
| `GET` | `/api/users/` | List users |
| `GET` | `/api/skills/` | List skills |
| `GET` | `/api/search/?q=query` | Search across all models |
| `GET` | `/api/me/live-status/` | Get current user's live status (badges, balances) |

### Payment Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/wallet/topup/` | Create Razorpay order for wallet top-up |
| `POST` | `/wallet/topup/verify/` | Verify Razorpay payment + credit wallet |
| `GET` | `/jobs/{id}/milestones/{id}/fund/` | Create order to fund a milestone |
| `POST` | `/webhooks/razorpay/` | Razorpay webhook (HMAC signed) |

### AI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/post/assist/` | AI-powered request drafting |
| `GET` | `/request/{id}/recommended-helpers/` | AI-matched helper suggestions |

### Authentication
- **Session**: Standard Django session auth (cookies)
- **API Key**: Send `Authorization: Api-Key <key>` header. Create keys at `/integrations/`.

### Rate Limits
- Anonymous: 100 requests/day
- Authenticated: 1,000 requests/day

---

## 🏗️ Architecture

```
HelperLearner/
├── accounts/           # User model, auth, trust scoring, GDPR export
├── marketplace/        # Core business logic
│   ├── models.py       # 30+ models (requests, jobs, milestones, escrow...)
│   ├── views.py        # Request/job CRUD, search, wallet, leaderboard
│   ├── advanced_views.py  # Portfolio, analytics, moderation, workspace
│   ├── payments.py     # Razorpay integration
│   ├── matching.py     # AI helper matching
│   ├── moderation.py   # Content moderation
│   ├── signals.py      # Lifecycle hooks, trust updates, emails
│   ├── webhooks.py     # Outgoing webhook dispatch
│   └── services.py     # Business logic (escrow, transfers)
├── notifications/      # Email templates, in-app notifs, Celery tasks
├── templates/          # Django templates (dark theme, responsive)
├── static/css/app.css  # 1600+ lines premium dark CSS
├── Dockerfile          # Production Docker image
├── docker-compose.yml  # Full stack (Django+PG+Redis+Celery)
└── .github/workflows/  # CI/CD pipeline
```

---

## 🧪 Testing

```bash
# Run all tests
python manage.py test

# Run specific test module
python manage.py test marketplace.tests_features
python manage.py test notifications.tests_email

# Current: 198+ tests passing
```

---

## 🌐 Deployment

### Render.com (Current)
The project is deployed on Render's free tier with auto-deploy from the `Different_High_Version` branch.

```yaml
# render.yaml defines the web service + PostgreSQL database
```

### Docker (Self-hosted)
```bash
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`python manage.py test`)
5. Push and create a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

**Built with ❤️ by [savinaysingh7](https://github.com/savinaysingh7)**
