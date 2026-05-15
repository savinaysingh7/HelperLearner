# HelperLearner - API Documentation

## 1. Overview

HelperLearner REST API provides JSON endpoints for mobile apps, external integrations, and client applications. All endpoints are RESTful and follow HTTP conventions.

**Base URL:** `https://helperlearner.com/api/v1/`
**Content-Type:** `application/json`
**Authentication:** Session-based or API Key

---

## 2. Authentication

### 2.1 Session Authentication
- Standard Django session auth (cookies)
- CSRF token required for POST/PUT/DELETE requests
- Session timeout: 30 days

### 2.2 API Key Authentication
```
Header: Authorization: Api-Key <key>
```
- Create API key in user dashboard → Integrations
- Keys are hashed in database (never shown again)
- Regenerate key if compromised

### 2.3 Rate Limiting
- **Anonymous users:** 100 requests/day
- **Authenticated users:** 1,000 requests/day
- **Premium users:** 10,000 requests/day

**Response Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1234567890
```

---

## 3. Help Requests API

### 3.1 List Help Requests

**Endpoint:** `GET /requests/`

**Query Parameters:**
```
- page: integer (default: 1)
- page_size: integer (default: 20, max: 100)
- status: string (open, claimed, resolved)
- difficulty: string (easy, medium, hard)
- min_kp: integer
- max_kp: integer
- tags: string (comma-separated)
- sort_by: string (created, kp_bounty, difficulty)
- search: string (full-text search)
```

**Request:**
```bash
curl -H "Authorization: Api-Key your-key" \
  "https://helperlearner.com/api/v1/requests/?status=open&difficulty=medium&sort_by=-created_at"
```

**Response:**
```json
{
  "count": 156,
  "next": "https://helperlearner.com/api/v1/requests/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "requester": {
        "id": 5,
        "username": "john_dev",
        "trust_score": 75.5
      },
      "title": "Django ORM Query Optimization",
      "description": "How to optimize N+1 queries in Django...",
      "kp_bounty": 150,
      "difficulty": "medium",
      "status": "open",
      "tags": ["django", "orm", "performance"],
      "created_at": "2024-05-10T14:30:00Z",
      "claimed_by": null,
      "claimed_at": null,
      "ai_summary": "User seeks help with optimizing Django ORM queries...",
      "views_count": 42,
      "solutions_count": 0
    }
  ]
}
```

### 3.2 Create Help Request

**Endpoint:** `POST /requests/`

**Request Body:**
```json
{
  "title": "How to implement JWT authentication in Django?",
  "description": "I need help setting up JWT for my API. Currently using basic auth...",
  "kp_bounty": 200,
  "difficulty": "medium",
  "tags": ["django", "jwt", "authentication"],
  "auto_generate_summary": true
}
```

**Response:** `201 Created`
```json
{
  "id": 157,
  "requester": { ... },
  "title": "How to implement JWT authentication in Django?",
  "kp_bounty": 200,
  "status": "open",
  "created_at": "2024-05-12T10:00:00Z",
  "ai_summary": "User is asking for help implementing JWT authentication..."
}
```

**Errors:**
- `400 Bad Request`: Invalid input (KP out of range, etc.)
- `401 Unauthorized`: Not authenticated
- `402 Payment Required`: Insufficient KP balance

### 3.3 Get Request Detail

**Endpoint:** `GET /requests/{id}/`

**Response:**
```json
{
  "id": 1,
  "requester": { ... },
  "title": "...",
  "kp_bounty": 150,
  "status": "claimed",
  "claimed_by": {
    "id": 8,
    "username": "helper_dev",
    "trust_score": 82.0
  },
  "claimed_at": "2024-05-11T09:15:00Z",
  "solutions": [
    {
      "id": 12,
      "helper_id": 8,
      "solution_text": "Use select_related() for foreign keys...",
      "created_at": "2024-05-11T10:00:00Z",
      "is_approved": false
    }
  ],
  "chat_thread_id": 5,
  "activity_log": [...]
}
```

### 3.4 Claim Request

**Endpoint:** `POST /requests/{id}/claim/`

**Response:** `200 OK`
```json
{
  "status": "success",
  "message": "Request claimed successfully",
  "request_id": 1,
  "chat_thread_id": 5
}
```

**Errors:**
- `400 Bad Request`: Request already claimed
- `404 Not Found`: Request not found
- `403 Forbidden`: User suspended or low trust score

### 3.5 Submit Solution

**Endpoint:** `POST /requests/{id}/submit-solution/`

**Request Body:**
```json
{
  "solution_text": "Here's how to optimize your queries...",
  "code_snippet": "# Python code\nMyModel.objects.select_related('foreign_key')..."
}
```

**Response:** `201 Created`
```json
{
  "solution_id": 12,
  "request_id": 1,
  "created_at": "2024-05-11T14:00:00Z",
  "status": "awaiting_review"
}
```

### 3.6 Rate Solution

**Endpoint:** `POST /requests/{id}/rate-solution/`

**Request Body:**
```json
{
  "solution_id": 12,
  "rating": 5,
  "comment": "Exactly what I needed! Clear explanation.",
  "approve": true
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "message": "Solution approved and KP transferred",
  "kp_transferred": 150,
  "helper_id": 8,
  "request_status": "resolved"
}
```

---

## 4. Freelance Jobs API

### 4.1 List Jobs

**Endpoint:** `GET /jobs/`

**Query Parameters:**
```
- page: integer
- status: string (open, assigned, in_progress, completed)
- min_budget: decimal
- max_budget: decimal
- sort_by: string (created, budget, deadline)
```

**Response:**
```json
{
  "count": 87,
  "results": [
    {
      "id": 1,
      "client": { ... },
      "title": "Build API for IoT Dashboard",
      "description": "Need Django REST API for...",
      "budget_inr": 50000,
      "status": "open",
      "deadline": "2024-06-30T23:59:59Z",
      "proposals_count": 5,
      "milestones": [
        {
          "id": 1,
          "title": "API Design & Setup",
          "amount_inr": 15000,
          "due_date": "2024-06-10"
        }
      ],
      "created_at": "2024-05-12T00:00:00Z"
    }
  ]
}
```

### 4.2 Create Job

**Endpoint:** `POST /jobs/`

**Request Body:**
```json
{
  "title": "Build React Dashboard for Analytics",
  "description": "Need a React dashboard showing real-time analytics...",
  "budget_inr": 75000,
  "deadline": "2024-07-15",
  "milestones": [
    {
      "title": "UI Design & Setup",
      "amount_inr": 25000,
      "due_date": "2024-06-20"
    },
    {
      "title": "Backend Integration",
      "amount_inr": 30000,
      "due_date": "2024-07-10"
    },
    {
      "title": "Testing & Deployment",
      "amount_inr": 20000,
      "due_date": "2024-07-15"
    }
  ],
  "required_skills": ["react", "nodejs", "postgresql"]
}
```

**Response:** `201 Created`
```json
{
  "id": 88,
  "client_id": 3,
  "title": "Build React Dashboard...",
  "budget_inr": 75000,
  "status": "open",
  "milestones": [...]
}
```

### 4.3 Submit Proposal

**Endpoint:** `POST /jobs/{id}/submit-proposal/`

**Request Body:**
```json
{
  "bid_amount_inr": 65000,
  "delivery_timeline_days": 30,
  "proposal_text": "I have 5+ years of React experience and completed similar projects..."
}
```

**Response:** `201 Created`
```json
{
  "proposal_id": 23,
  "job_id": 88,
  "contractor_id": 10,
  "status": "submitted"
}
```

### 4.4 Accept Proposal

**Endpoint:** `POST /jobs/{id}/accept-proposal/`

**Request Body:**
```json
{
  "proposal_id": 23
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "job_status": "assigned",
  "contractor_id": 10,
  "first_milestone_id": 1
}
```

### 4.5 Fund Milestone (Escrow)

**Endpoint:** `POST /jobs/{id}/milestones/{milestone_id}/fund/`

**Creates Razorpay Order:**
```json
{
  "order_id": "order_...",
  "amount": 25000,
  "currency": "INR",
  "razorpay_key_id": "rzp_test_...",
  "client": {
    "name": "John Developer",
    "email": "john@example.com"
  }
}
```

**Frontend handles Razorpay checkout → Server verifies payment**

### 4.6 Submit Deliverable

**Endpoint:** `POST /jobs/{id}/milestones/{milestone_id}/submit-deliverable/`

**Request Body:**
```json
{
  "submission_text": "Completed the API endpoints as per requirements...",
  "file_upload_url": "https://s3.../deliverable.zip"
}
```

**Response:** `201 Created`
```json
{
  "deliverable_id": 45,
  "milestone_id": 1,
  "status": "submitted",
  "awaiting_client_review": true
}
```

### 4.7 Approve Milestone (Release Escrow)

**Endpoint:** `POST /jobs/{id}/milestones/{milestone_id}/approve/`

**Request Body:**
```json
{
  "approval_notes": "Excellent work! Exactly as specified.",
  "rating": 5
}
```

**Response:** `200 OK`
```json
{
  "status": "approved",
  "amount_released_inr": 25000,
  "contractor_wallet_updated": true,
  "next_milestone_id": 2
}
```

---

## 5. Payments API

### 5.1 Create Wallet Top-Up Order

**Endpoint:** `POST /wallet/topup/`

**Request Body:**
```json
{
  "amount_inr": 5000
}
```

**Response:**
```json
{
  "order_id": "order_...",
  "amount": 5000,
  "currency": "INR",
  "razorpay_key": "rzp_test_..."
}
```

### 5.2 Verify Payment & Credit Wallet

**Endpoint:** `POST /wallet/topup/verify/`

**Request Body:**
```json
{
  "razorpay_order_id": "order_...",
  "razorpay_payment_id": "pay_...",
  "razorpay_signature": "..."
}
```

**Response:** `200 OK`
```json
{
  "status": "success",
  "amount_credited": 5000,
  "new_balance": 12500,
  "transaction_id": "txn_..."
}
```

**Errors:**
- `400 Bad Request`: Invalid signature (fraud detected!)
- `409 Conflict`: Duplicate payment (idempotent check)

### 5.3 Get Wallet Balance

**Endpoint:** `GET /wallet/balance/`

**Response:**
```json
{
  "wallet_inr": 12500.00,
  "knowledge_points": 350,
  "pending_withdrawals": 5000,
  "available_for_withdrawal": 7500
}
```

### 5.4 Request Withdrawal

**Endpoint:** `POST /wallet/withdraw/`

**Request Body:**
```json
{
  "amount_inr": 5000,
  "bank_account_id": 1
}
```

**Response:** `201 Created`
```json
{
  "withdrawal_id": "wd_123",
  "amount_inr": 5000,
  "status": "pending",
  "expected_delivery": "2024-05-15"
}
```

---

## 6. Users API

### 6.1 Get User Profile

**Endpoint:** `GET /users/{id}/`

**Response:**
```json
{
  "id": 5,
  "username": "john_dev",
  "email": "john@example.com",
  "bio": "Full-stack developer with 5+ years experience",
  "skills": ["django", "react", "postgresql"],
  "knowledge_points": 350,
  "trust_score": 78.5,
  "badges": ["helpful_contributor", "reliable_contractor"],
  "stats": {
    "requests_resolved": 42,
    "jobs_completed": 8,
    "average_rating": 4.7,
    "member_since": "2023-01-15"
  },
  "portfolio": {
    "featured_projects": [...],
    "achievements": [...]
  }
}
```

### 6.2 Update Profile

**Endpoint:** `PATCH /users/me/`

**Request Body:**
```json
{
  "bio": "Updated bio",
  "skills": ["django", "react", "postgres", "kubernetes"],
  "notification_preference": "email"
}
```

**Response:** `200 OK`

### 6.3 Get Current User

**Endpoint:** `GET /users/me/`

**Returns:** Full profile including private data (email, wallet, etc.)

### 6.4 Get User's Live Status

**Endpoint:** `GET /users/me/live-status/`

**Response:**
```json
{
  "kp_balance": 350,
  "wallet_inr": 12500.00,
  "pending_requests": 3,
  "pending_jobs": 2,
  "unread_notifications": 5,
  "active_chat_threads": 7,
  "trust_score": 78.5,
  "is_suspended": false
}
```

---

## 7. Search API

### 7.1 Global Search

**Endpoint:** `GET /search/`

**Query Parameters:**
```
- q: string (required)
- category: string (requests, jobs, users)
- limit: integer (default: 50, max: 100)
- offset: integer (default: 0)
```

**Request:**
```bash
curl "https://helperlearner.com/api/v1/search/?q=django%20authentication&category=requests"
```

**Response:**
```json
{
  "results": {
    "requests": [
      {
        "id": 1,
        "type": "help_request",
        "title": "How to implement Django authentication?",
        "score": 0.95
      }
    ],
    "jobs": [
      {
        "id": 88,
        "type": "freelance_job",
        "title": "Build API with Django authentication",
        "score": 0.87
      }
    ],
    "users": [
      {
        "id": 5,
        "type": "user",
        "username": "django_expert",
        "score": 0.72
      }
    ]
  }
}
```

---

## 8. Notification API

### 8.1 List Notifications

**Endpoint:** `GET /notifications/`

**Query Parameters:**
```
- unread_only: boolean (default: false)
- limit: integer (default: 20)
```

**Response:**
```json
{
  "unread_count": 3,
  "results": [
    {
      "id": 101,
      "type": "request_claimed",
      "title": "Your request was claimed",
      "message": "john_dev has claimed your Django ORM question",
      "related_object": "/api/v1/requests/1/",
      "created_at": "2024-05-12T10:00:00Z",
      "is_read": false
    }
  ]
}
```

### 8.2 Mark as Read

**Endpoint:** `POST /notifications/{id}/read/`

**Response:** `204 No Content`

---

## 9. Chat API

### 9.1 Get Chat Thread

**Endpoint:** `GET /chat/threads/{id}/`

**Response:**
```json
{
  "id": 5,
  "request_id": 1,
  "subject": "Django ORM Query Optimization",
  "participants": [...],
  "messages": [
    {
      "id": 23,
      "sender": { ... },
      "content": "How to optimize N+1 queries?",
      "created_at": "2024-05-11T10:00:00Z",
      "is_read": true
    }
  ]
}
```

### 9.2 Send Message

**Endpoint:** `POST /chat/threads/{id}/messages/`

**Request Body:**
```json
{
  "content": "Try using select_related() for this query",
  "mentions": [5, 8]
}
```

**Response:** `201 Created`
(WebSocket broadcasts to other participants in real-time)

---

## 10. Error Handling

### Standard Error Response

```json
{
  "error": true,
  "error_code": "INSUFFICIENT_KP",
  "message": "You don't have enough KP to post this request",
  "details": {
    "required_kp": 150,
    "available_kp": 100
  },
  "timestamp": "2024-05-12T10:30:00Z"
}
```

### Common Error Codes

| Code | HTTP Status | Message |
|------|------------|---------|
| INVALID_INPUT | 400 | Request body validation failed |
| UNAUTHORIZED | 401 | Authentication required |
| INSUFFICIENT_KP | 402 | Not enough Knowledge Points |
| FORBIDDEN | 403 | You don't have permission |
| NOT_FOUND | 404 | Resource not found |
| CONFLICT | 409 | Request conflicts with current state |
| RATE_LIMITED | 429 | Too many requests |
| SERVER_ERROR | 500 | Internal server error |

---

## 11. Pagination

All list endpoints support pagination:

```
?page=1&page_size=20
```

Response includes:
```json
{
  "count": 156,
  "next": "https://...?page=2",
  "previous": null,
  "results": [...]
}
```

---

## 12. WebSocket Events (Real-time)

**Connection:** `wss://helperlearner.com/ws/chat/{thread_id}/`

**Events:**
```json
{
  "type": "message",
  "data": {
    "id": 23,
    "sender_id": 5,
    "content": "...",
    "created_at": "2024-05-12T10:00:00Z"
  }
}
```

**Broadcast Events:**
- `message_sent`: New chat message
- `request_claimed`: Help request claimed
- `milestone_approved`: Job milestone approved (funds released)
- `notification_created`: In-app notification

---

## Complete API Reference Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /requests/ | Any | List help requests |
| POST | /requests/ | Auth | Create help request |
| GET | /requests/{id}/ | Any | Get request detail |
| POST | /requests/{id}/claim/ | Auth | Claim request |
| POST | /requests/{id}/submit-solution/ | Auth | Submit solution |
| POST | /requests/{id}/rate-solution/ | Auth | Rate solution |
| GET | /jobs/ | Any | List freelance jobs |
| POST | /jobs/ | Auth | Create job |
| POST | /jobs/{id}/submit-proposal/ | Auth | Submit proposal |
| POST | /jobs/{id}/accept-proposal/ | Auth | Accept proposal |
| POST | /jobs/{id}/milestones/{mid}/fund/ | Auth | Fund milestone (Razorpay) |
| POST | /wallet/topup/ | Auth | Create top-up order |
| POST | /wallet/topup/verify/ | Auth | Verify & credit wallet |
| GET | /users/{id}/ | Any | Get user profile |
| GET | /users/me/ | Auth | Get current user |
| GET | /search/ | Any | Global search |
| GET | /notifications/ | Auth | List notifications |
| POST | /chat/threads/{id}/messages/ | Auth | Send message |

---

**API Version:** v1
**Last Updated:** May 2024
**Status:** Production Ready
