# HelperLearner - Database Schema & Entity Relationship Diagram

## 1. Entity Relationship Diagram (ER Diagram)

![Entity Relationship Diagram — Complete database entity relationships with color-coded groups](screenshots/Entity%20Relationship.png)

```
┌─────────────────────────┐
│     CustomUser          │ (Django User + Extended)
├─────────────────────────┤
│ PK: id                  │
│ username (unique)       │
│ email (unique)          │
│ bio                     │
│ knowledge_points        │
│ wallet_inr              │
│ trust_score             │
│ is_suspended            │
│ compliance_verified     │
│ created_at              │
│ updated_at              │
└────────────────┬────────┘
                 │
    ┌────────────┼────────────┬─────────────┐
    │ 1-N        │ 1-N        │ 1-N         │
    │            │            │             │
┌───┴─────────┐  │  ┌────────┴──┐  ┌──────┴────┐
│Help Request │  │  │Freelance  │  │  Chat     │
│ (Requester) │  │  │ Job       │  │ Message   │
└─────────────┘  │  │(Client)   │  └───────────┘
                 │  └───────────┘
    ┌────────────┼─────────────┐
    │ 1-N        │             │
    │            │ 1-N (helper)│
    │  ┌─────────┴──────────────┐
    │  │                        │
    │  ▼                        ▼
    │ (Claimed by)        (Contractor)
    │
┌───┴────────────────────────────────┐
│      TrustSignal                   │
├────────────────────────────────────┤
│ PK: id                             │
│ FK: user_id → CustomUser           │
│ signal_type                        │
│ score_delta                        │
│ created_at                         │
└────────────────────────────────────┘

┌─────────────────────────┐
│   Skill                 │
├─────────────────────────┤
│ PK: id                  │
│ name (unique)           │
│ category                │
│ description             │
│ proficiency_levels      │
└────────────────────────┴──────────────────┐
                 ▲ M-N Relationship         │
                 │ (through UserSkill)      │
                 │                          │
            ┌────┴──────────────────────────┤
            │   CustomUser.skills (M2M)     │
```

---

## 2. Table Schemas (SQL DDL)

### 2.1 Authentication & User Management

```sql
-- CustomUser (Extended Django User Model)
CREATE TABLE auth_user (
    id SERIAL PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    password VARCHAR(128) NOT NULL,
    first_name VARCHAR(150),
    last_name VARCHAR(150),
    is_staff BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP,
    date_joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE accounts_customuser (
    -- Inherits from auth_user
    user_ptr_id INTEGER PRIMARY KEY REFERENCES auth_user(id) ON DELETE CASCADE,
    bio TEXT,
    knowledge_points INTEGER DEFAULT 100 CHECK (knowledge_points >= 0),
    last_kp_claim TIMESTAMP,
    wallet_inr NUMERIC(12,2) DEFAULT 0.00 CHECK (wallet_inr >= 0),
    trust_score FLOAT DEFAULT 0.0,
    trust_score_updated_at TIMESTAMP,
    compliance_verified BOOLEAN DEFAULT FALSE,
    is_suspended BOOLEAN DEFAULT FALSE,
    suspended_until TIMESTAMP,
    suspension_reason VARCHAR(255),
    notification_preference VARCHAR(12) DEFAULT 'both',
    ui_density VARCHAR(12) DEFAULT 'comfortable',
    notify_requests BOOLEAN DEFAULT TRUE,
    notify_jobs BOOLEAN DEFAULT TRUE,
    notify_chat BOOLEAN DEFAULT TRUE,
    notify_kp BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_knowledge_points (knowledge_points),
    INDEX idx_wallet_inr (wallet_inr),
    INDEX idx_trust_score (trust_score),
    INDEX idx_is_suspended (is_suspended)
);

-- Skill Model
CREATE TABLE marketplace_skill (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50),
    description TEXT,
    proficiency_levels VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UserSkill (M2M through table)
CREATE TABLE accounts_customuser_skills (
    id SERIAL PRIMARY KEY,
    customuser_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    skill_id INTEGER NOT NULL REFERENCES marketplace_skill(id),
    UNIQUE(customuser_id, skill_id)
);
```

### 2.2 Help Request System

```sql
-- HelpRequest Model
CREATE TABLE marketplace_helprequest (
    id SERIAL PRIMARY KEY,
    requester_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    kp_bounty INTEGER NOT NULL CHECK (kp_bounty BETWEEN 1 AND 1000),
    difficulty VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(50) DEFAULT 'open',
    tags VARCHAR(255),
    ai_summary TEXT,
    search_vector tsvector,  -- For full-text search
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    claimed_by_id INTEGER REFERENCES accounts_customuser(user_ptr_id),
    claimed_at TIMESTAMP,
    resolved_at TIMESTAMP,
    expires_at TIMESTAMP,
    
    -- Indexes
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_claimed_by (claimed_by_id),
    FULLTEXT INDEX idx_search_vector (search_vector)
);

-- Solution Model
CREATE TABLE marketplace_solution (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES marketplace_helprequest(id),
    helper_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    solution_text TEXT NOT NULL,
    code_snippet TEXT,
    is_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approval_rating INTEGER,  -- 1-5 stars
    approval_comment TEXT
);

-- Rating Model
CREATE TABLE marketplace_rating (
    id SERIAL PRIMARY KEY,
    rater_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    ratee_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment TEXT,
    content_type VARCHAR(50),  -- 'help_request' or 'freelance_job'
    object_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(rater_id, ratee_id, object_id)
);

-- Comment Model
CREATE TABLE marketplace_comment (
    id SERIAL PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    request_id INTEGER REFERENCES marketplace_helprequest(id),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);
```

### 2.3 Freelance Job System

```sql
-- FreelanceJob Model
CREATE TABLE marketplace_freelancejob (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    budget_inr NUMERIC(12,2) NOT NULL CHECK (budget_inr > 0),
    status VARCHAR(50) DEFAULT 'open',
    deadline TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contractor_id INTEGER REFERENCES accounts_customuser(user_ptr_id),
    contract_status VARCHAR(50),
    
    INDEX idx_status (status),
    INDEX idx_deadline (deadline),
    INDEX idx_client_id (client_id)
);

-- Proposal Model (Contractors bid on jobs)
CREATE TABLE marketplace_proposal (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES marketplace_freelancejob(id),
    contractor_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    bid_amount_inr NUMERIC(12,2) NOT NULL,
    delivery_timeline_days INTEGER,
    proposal_text TEXT,
    status VARCHAR(50) DEFAULT 'submitted',  -- submitted, accepted, rejected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(job_id, contractor_id)
);

-- Milestone Model (Stages of a job)
CREATE TABLE marketplace_milestone (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES marketplace_freelancejob(id),
    milestone_number INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    deliverable_description TEXT NOT NULL,
    amount_inr NUMERIC(12,2) NOT NULL,
    due_date TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, in_progress, delivered, approved, paid
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_job_id (job_id),
    INDEX idx_status (status)
);

-- Deliverable Model (Work submitted for milestone)
CREATE TABLE marketplace_deliverable (
    id SERIAL PRIMARY KEY,
    milestone_id INTEGER NOT NULL REFERENCES marketplace_milestone(id),
    contractor_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    submission_text TEXT,
    file_upload_url VARCHAR(500),
    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'submitted',  -- submitted, approved, revision_requested
    approval_notes TEXT,
    
    INDEX idx_milestone_id (milestone_id)
);
```

### 2.4 Payment & Escrow System

```sql
-- EscrowTransaction Model
CREATE TABLE marketplace_escrowtransaction (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES marketplace_freelancejob(id),
    milestone_id INTEGER NOT NULL REFERENCES marketplace_milestone(id),
    amount_inr NUMERIC(12,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'locked',  -- locked, released, refunded, disputed
    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP,
    refunded_at TIMESTAMP,
    
    -- Razorpay Integration
    razorpay_order_id VARCHAR(100),
    razorpay_payment_id VARCHAR(100),
    razorpay_signature VARCHAR(255),
    payment_verified BOOLEAN DEFAULT FALSE,
    
    -- Audit
    transaction_hash UUID UNIQUE NOT NULL,  -- Prevent duplicates
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_status (status),
    INDEX idx_job_id (job_id),
    INDEX idx_milestone_id (milestone_id)
);

-- WalletTransaction Model
CREATE TABLE marketplace_wallettransaction (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    transaction_type VARCHAR(50),  -- 'credit', 'debit', 'withdrawal'
    amount_inr NUMERIC(12,2) NOT NULL,
    description VARCHAR(255),
    escrow_transaction_id INTEGER REFERENCES marketplace_escrowtransaction(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Withdrawal Request Model
CREATE TABLE marketplace_withdrawalrequest (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    amount_inr NUMERIC(12,2) NOT NULL,
    bank_account_id INTEGER,  -- Reference to encrypted bank details
    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, completed, rejected
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    transaction_id VARCHAR(100),  -- Bank transaction reference
    notes TEXT,
    
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
```

### 2.5 Trust & Reputation

```sql
-- TrustSignal Model
CREATE TABLE marketplace_trustsignal (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    signal_type VARCHAR(50) NOT NULL,  -- 'rating', 'proposal', 'dispute', 'tenure'
    score_delta INTEGER NOT NULL,
    related_object_id INTEGER,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- For time-decaying signals
    
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Dispute Model
CREATE TABLE marketplace_dispute (
    id SERIAL PRIMARY KEY,
    raised_by_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    job_id INTEGER REFERENCES marketplace_freelancejob(id),
    milestone_id INTEGER REFERENCES marketplace_milestone(id),
    reason VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'open',  -- open, in_review, resolved, closed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    resolved_by_id INTEGER REFERENCES accounts_customuser(user_ptr_id),
    
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

### 2.6 Communication

```sql
-- ChatThread Model
CREATE TABLE marketplace_chatthread (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES marketplace_helprequest(id),
    job_id INTEGER REFERENCES marketplace_freelancejob(id),
    workspace_id INTEGER REFERENCES marketplace_workspace(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    subject VARCHAR(255),
    
    INDEX idx_request_id (request_id),
    INDEX idx_job_id (job_id)
);

-- ChatThread Participants (M2M)
CREATE TABLE marketplace_chatthread_participants (
    id SERIAL PRIMARY KEY,
    chatthread_id INTEGER NOT NULL REFERENCES marketplace_chatthread(id),
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(chatthread_id, user_id)
);

-- ChatMessage Model
CREATE TABLE marketplace_chatmessage (
    id SERIAL PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES marketplace_chatthread(id),
    sender_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    content TEXT NOT NULL,
    file_attachment_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    read_by_ids TEXT,  -- JSON array of user IDs who read this message
    
    INDEX idx_thread_id (thread_id),
    INDEX idx_created_at (created_at)
);

-- Notification Model
CREATE TABLE notifications_notification (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    notification_type VARCHAR(50),  -- 'request_claimed', 'job_proposal', 'milestone_approved'
    content_type VARCHAR(50),  -- 'help_request', 'freelance_job', etc.
    object_id INTEGER,
    title VARCHAR(255),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_id (user_id),
    INDEX idx_is_read (is_read),
    INDEX idx_created_at (created_at)
);
```

### 2.7 Workspace & Collaboration

```sql
-- Workspace Model
CREATE TABLE marketplace_workspace (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_owner_id (owner_id)
);

-- Workspace Members (M2M)
CREATE TABLE marketplace_workspace_members (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES marketplace_workspace(id),
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    role VARCHAR(50) DEFAULT 'developer',  -- owner, maintainer, developer
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(workspace_id, user_id)
);

-- Sprint Model
CREATE TABLE marketplace_sprint (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES marketplace_workspace(id),
    name VARCHAR(255) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'open',  -- open, in_progress, completed
    goal TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_workspace_id (workspace_id)
);

-- Issue/Task Model
CREATE TABLE marketplace_issue (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES marketplace_workspace(id),
    sprint_id INTEGER REFERENCES marketplace_sprint(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    assigned_to_id INTEGER REFERENCES accounts_customuser(user_ptr_id),
    status VARCHAR(50) DEFAULT 'todo',  -- todo, in_progress, done
    priority VARCHAR(20) DEFAULT 'medium',
    created_by_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_workspace_id (workspace_id),
    INDEX idx_sprint_id (sprint_id),
    INDEX idx_status (status)
);
```

### 2.8 AI & Moderation

```sql
-- AIAssistanceLog Model
CREATE TABLE marketplace_aiassistancelog (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    request_id INTEGER REFERENCES marketplace_helprequest(id),
    assistance_type VARCHAR(50),  -- 'summary', 'matching', 'moderation'
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd NUMERIC(10,4),
    response_json TEXT,
    status VARCHAR(50),  -- 'success', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- ContentFlag Model (Moderation)
CREATE TABLE marketplace_contentflag (
    id SERIAL PRIMARY KEY,
    reported_by_id INTEGER NOT NULL REFERENCES accounts_customuser(user_ptr_id),
    content_type VARCHAR(50),  -- 'help_request', 'freelance_job', 'comment'
    object_id INTEGER NOT NULL,
    reason VARCHAR(50),  -- 'spam', 'hate_speech', 'scam'
    description TEXT,
    status VARCHAR(50) DEFAULT 'open',  -- open, in_review, resolved
    moderator_notes TEXT,
    action_taken VARCHAR(50),  -- 'none', 'warning', 'content_removed', 'user_suspended'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

---

## 3. Key Indexes for Performance

```sql
-- User Queries
CREATE INDEX idx_customuser_email ON accounts_customuser(email);
CREATE INDEX idx_customuser_trust_score ON accounts_customuser(trust_score DESC);
CREATE INDEX idx_customuser_created_at ON accounts_customuser(created_at);

-- HelpRequest Queries
CREATE INDEX idx_helprequest_status_created ON marketplace_helprequest(status, created_at DESC);
CREATE INDEX idx_helprequest_claimed_by_status ON marketplace_helprequest(claimed_by_id, status);
CREATE INDEX idx_helprequest_requester_status ON marketplace_helprequest(requester_id, status);

-- FreelanceJob Queries
CREATE INDEX idx_freelancejob_status_deadline ON marketplace_freelancejob(status, deadline);
CREATE INDEX idx_freelancejob_client_status ON marketplace_freelancejob(client_id, status);
CREATE INDEX idx_freelancejob_contractor ON marketplace_freelancejob(contractor_id);

-- Payment Queries
CREATE INDEX idx_escrow_job_status ON marketplace_escrowtransaction(job_id, status);
CREATE INDEX idx_wallet_transaction_user_date ON marketplace_wallettransaction(user_id, created_at DESC);

-- Communication Queries
CREATE INDEX idx_chatmessage_thread_date ON marketplace_chatmessage(thread_id, created_at DESC);
CREATE INDEX idx_notification_user_read_date ON notifications_notification(user_id, is_read, created_at DESC);

-- Search (Full-text)
CREATE INDEX idx_helprequest_search_vector ON marketplace_helprequest USING GIN(search_vector);
CREATE INDEX idx_freelancejob_search_vector ON marketplace_freelancejob USING GIN(search_vector);
```

---

## 4. Database Constraints

```sql
-- Foreign Key Constraints
ALTER TABLE marketplace_helprequest ADD CONSTRAINT fk_requester 
    FOREIGN KEY (requester_id) REFERENCES accounts_customuser(user_ptr_id);

ALTER TABLE marketplace_helprequest ADD CONSTRAINT fk_claimed_by 
    FOREIGN KEY (claimed_by_id) REFERENCES accounts_customuser(user_ptr_id);

-- Check Constraints
ALTER TABLE accounts_customuser ADD CONSTRAINT check_kp_non_negative 
    CHECK (knowledge_points >= 0);

ALTER TABLE accounts_customuser ADD CONSTRAINT check_wallet_non_negative 
    CHECK (wallet_inr >= 0.00);

ALTER TABLE marketplace_helprequest ADD CONSTRAINT check_kp_bounty_range 
    CHECK (kp_bounty BETWEEN 1 AND 1000);

ALTER TABLE marketplace_rating ADD CONSTRAINT check_rating_range 
    CHECK (score BETWEEN 1 AND 5);

-- Unique Constraints
ALTER TABLE accounts_customuser ADD CONSTRAINT unique_username UNIQUE (username);
ALTER TABLE accounts_customuser ADD CONSTRAINT unique_email UNIQUE (email);
ALTER TABLE marketplace_escrowtransaction ADD CONSTRAINT unique_transaction_hash UNIQUE (transaction_hash);
```

---

## 5. Normalization & Query Optimization

**Normalization Level:** 3NF (Third Normal Form)
- No transitive dependencies
- All non-key attributes depend on primary key
- No partial dependencies

**Denormalization Strategies (for performance):**
- `CustomUser.trust_score`: Cached, updated via signals
- `HelpRequest.ai_summary`: Pre-computed once
- `CustomUser.knowledge_points`: Real-time but critical, frequent reads
- `Notification.is_read`: Frequently queried, indexed

---

## Summary

The HelperLearner database:
- ✅ Normalized to 3NF
- ✅ 20+ tables covering all business logic
- ✅ Proper foreign key relationships
- ✅ Comprehensive indexes for common queries
- ✅ ACID properties via PostgreSQL
- ✅ Audit columns (created_at, updated_at)
- ✅ Supports horizontal scaling (via sharding on user_id if needed)
