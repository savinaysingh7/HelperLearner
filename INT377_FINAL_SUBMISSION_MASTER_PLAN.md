# INT377: DevOps Transformation Guide for HelperLearner
## "Automation, Monitoring, and Self-Healing"
### Final Submission & Study Master Plan (Units I-V)

---

## 1. The Big Picture (DevOps Architecture)
To get the best marks, you must show the "Flow."
1. **Developer pushes code to GitHub.**
2. **GitHub tells Jenkins** (Automation).
3. **Jenkins builds a Docker image** (Containerization).
4. **Jenkins deploys it to Kubernetes** (Orchestration).
5. **Kubernetes restarts the app if it crashes** (Self-Healing).
6. **Prometheus/Grafana show the app's health** (Monitoring).

---

## 2. Unit I: Cloud & Git Fundamentals
**Concept:** Cloud computing is the on-demand delivery of IT resources over the internet.

### 2.1 Cloud Delivery Models
*   **IaaS (Infrastructure as a Service):** We use this for our **Servers (EC2/VMs)**.
*   **PaaS (Platform as a Service):** We use this for our **Database (RDS)**.
*   **SaaS (Software as a Service):** We use **GitHub** and **Slack/Email** tools.

### 2.2 Cloud Deployment Models
*   **Public Cloud:** Our project is on the Public Cloud (AWS/GCP/Render) because it's cost-effective and scalable.
*   **Private Cloud:** Used by banks/governments for high security.
*   **Hybrid:** A mix of both.
*   **Community:** Shared by organizations with common goals (e.g., Universities).

### 2.3 Git Governance
```bash
git checkout -b feature/devops-automation  # Create new branch
git add .                                  # Stage all changes
git commit -m "Initial DevOps setup"       # Save locally
git push origin feature/devops-automation  # Send to GitHub
```

---

## 3. Unit II: Virtualization & Containerization
**Concept:** Virtualization allows one physical server to run many "Virtual Machines" (VMs).

### 3.1 Hypervisors (The "Managers")
*   **Type 1 (Bare Metal):** Runs directly on hardware (e.g., VMware ESXi, Xen).
*   **Type 2 (Hosted):** Runs on an OS (e.g., VirtualBox, VMware Workstation).
*   **Containers (Docker):** Faster than VMs because they share the Host OS Kernel.

### 3.2 Optimized Dockerfile (Multi-stage)
```dockerfile
# Stage 1: Build
FROM python:3.12-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Run
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

---

## 4. Unit III: IaC & Cloud Economics
**Concept:** We use code to manage infrastructure so it's repeatable.

### 4.1 Terraform (IaC)
```hcl
resource "aws_instance" "hl_server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
}
```

### 4.2 Cloud Service Comparison Table (Viva Gold!)
| Service | AWS | GCP | OpenStack (Private) |
| --- | --- | --- | --- |
| **Compute** | EC2 | Compute Engine | Nova |
| **Storage** | S3 | Cloud Storage | Swift |
| **Network** | VPC | VPC Network | Neutron |

### 4.3 Cloud Economics (TCO)
*   **TCO (Total Cost of Ownership):** Includes not just server price, but also electricity, cooling, and staff costs.
*   **Billing:** AWS uses "Pay-as-you-go." We save money by turning off servers when not in use.

### 4.4 AWS Cost Protection & 24/7 Uptime (Free Tier Strategy)
**Concept:** Real DevOps environments run 24/7, but we must protect our budget.
*   **The 750 Hours Rule:** The AWS Free Tier gives you 750 hours of EC2 (server) usage per month. Since a month has roughly 744 hours (24 hours * 31 days), this means you can run **one** small server (`t2.micro` or `t3.micro`) **24/7 for the entire month for free**.
*   **Uptime & Continuous Integration:** Jenkins (our automation tool) watches GitHub 24 hours a day. The moment you push code, the pipeline starts.
*   **Billing Alarms (Crucial Step):** Before creating any servers, we set up an AWS CloudWatch Billing Alarm. If our bill ever exceeds $0.10 (₹8), AWS immediately sends an email alert, preventing accidental charges.

---

## 5. Unit IV: CI/CD (Automation)
**Concept:** Automating the "Build -> Test -> Deploy" cycle.

### The Jenkinsfile
```groovy
pipeline {
    agent any
    stages {
        stage('Test') { steps { sh 'pytest' } }
        stage('Build Image') { steps { sh 'docker build -t hl:v1 .' } }
        stage('Self-Healing Deploy') { steps { sh 'kubectl apply -f k8s.yaml' } }
    }
}
```

---

## 6. Unit V: Security & Monitoring
**Concept:** You can't manage what you don't measure.

### 6.1 Shared Responsibility Model
*   **Cloud Provider (AWS):** Responsible for security **OF** the cloud (Hardware, Data centers).
*   **Customer (Us):** Responsible for security **IN** the cloud (Our app, data, passwords).

### 6.2 Monitoring (The "Eyes")
*   **Prometheus:** Pulls metrics from the app.
*   **Grafana:** Displays the "Health Dashboard."

### 6.3 Security (IAM)
*   **IAM (Identity & Access Management):** Giving the "Least Privilege." Don't give full admin rights to every developer.

---

## 7. Applied Syllabus Concepts: Free Implementation Steps

### From Unit I: Git & DevOps Fundamentals
**Applied Concepts:** Git Lifecycle, Remote Repositories, DevOps delivery pipelines

#### 7.1 Git Workflow Implementation (ALREADY ACTIVE)
```bash
# Step 1: Initialize repository structure
git init
git remote add origin https://github.com/yourusername/HelperLearner.git

# Step 2: Create feature branches for each DevOps component
git checkout -b feature/docker-setup
git checkout -b feature/github-actions-ci
git checkout -b feature/monitoring-setup

# Step 3: Enforce branch protection rules in GitHub
# Go to: Settings → Branches → Add rule for 'main'
# - Require pull request reviews
# - Require status checks to pass

# Step 4: Commit message standards (DevOps best practice)
git commit -m "feat(docker): Add multi-stage Dockerfile for HelperLearner

- Reduce image size using multi-stage build
- Optimize layers for caching efficiency"
```

**Free Tools Used:** GitHub (built-in Git hosting)

---

### From Unit II: Containerization & Docker
**Applied Concepts:** Docker Architecture, Image Optimization, Container Lifecycle

#### 7.2 Docker Implementation Steps

**Step 1: Create Optimized Dockerfile (Already in plan - see section 3.2)**

**Step 2: Build and Test Docker Image Locally**
```bash
# Navigate to project root
cd c:\Users\savin\Documents\02_Learning_and_Practice\Python & Django\HelperLearner.worktrees\agents-syllabus-implementation-steps

# Build the image
docker build -t helperlearner:latest .

# Run container locally
docker run -p 8000:8000 helperlearner:latest

# Verify app runs at http://localhost:8000
```

**Step 3: Optimize Layers for Faster CI/CD**
```dockerfile
# Best practice: Order layers from least to most frequently changed
FROM python:3.12-slim

WORKDIR /app

# Copy requirements first (changes rarely)
COPY requirements.txt .

# Install dependencies in one layer
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update && \
    apt-get install -y postgresql-client && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application code (changes frequently)
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "helperlearner_root.wsgi:application"]
```

**Free Tools Used:** Docker Desktop (free community edition)

---

### From Unit III: Infrastructure as Code (IaC)
**Applied Concepts:** IaC Principles, Cloud Economics, Free Tier Optimization

#### 7.3 Docker Compose as IaC (Free Alternative to Terraform)

**File: `docker-compose.yml` (Infrastructure as Code)**
```yaml
version: '3.8'
services:
  web:
    build: .
    container_name: helperlearner_web
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=localhost,127.0.0.1
      - DATABASE_URL=postgresql://user:password@db:5432/helperlearner
    depends_on:
      - db
    volumes:
      - ./:/app
    command: gunicorn --bind 0.0.0.0:8000 helperlearner_root.wsgi:application

  db:
    image: postgres:15-alpine
    container_name: helperlearner_db
    environment:
      - POSTGRES_DB=helperlearner
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

**Implementation Steps:**
```bash
# Step 1: Install Docker Compose (usually comes with Docker Desktop)
docker-compose --version

# Step 2: Start entire stack with one command
docker-compose up -d

# Step 3: Verify services are running
docker-compose ps

# Step 4: View logs
docker-compose logs -f web

# Step 5: Stop everything
docker-compose down
```

**Cost Analysis:**
- Running on your local machine: **$0** (free)
- If deployed to cloud: Use AWS Free Tier (750 hours EC2 t2.micro/t3.micro)

**Free Tools Used:** Docker Compose (included with Docker)

---

### From Unit IV: CI/CD Pipelines
**Applied Concepts:** Continuous Integration, Automated Testing & Deployment

#### 7.4 GitHub Actions CI/CD Pipeline (FREE!)

**File: `.github/workflows/ci-cd.yml`**
```yaml
name: HelperLearner CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: helperlearner_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
        cache: 'pip'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt pytest pytest-cov
    
    - name: Run migrations
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/helperlearner_test
      run: |
        python manage.py migrate
    
    - name: Run tests with coverage
      env:
        DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/helperlearner_test
      run: |
        pytest --cov=. --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  build:
    needs: test
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: |
        docker build -t helperlearner:latest .
        docker build -t helperlearner:${{ github.sha }} .
    
    - name: Run container health check
      run: |
        docker run -d -p 8000:8000 helperlearner:latest
        sleep 5
        curl -f http://localhost:8000/health || exit 1
```

**Implementation Steps:**
```bash
# Step 1: Create GitHub Actions directory
mkdir -p .github/workflows

# Step 2: Create the workflow file (ci-cd.yml) in the path above

# Step 3: Push to GitHub
git add .github/
git commit -m "ci: Add GitHub Actions CI/CD pipeline"
git push origin main

# Step 4: Monitor pipeline
# Go to GitHub repository → Actions tab
# Watch workflow execute automatically on each push
```

**Free Tools Used:** GitHub Actions (2,000 free minutes/month for public repos)

---

### From Unit V: Monitoring & Observability
**Applied Concepts:** Logs, Metrics, Dashboards, Security in CI/CD

#### 7.5 Monitoring Stack with Prometheus & Grafana (FREE)

**Step 1: Add Django Monitoring Middleware**
```python
# In helperlearner_root/settings.py

INSTALLED_APPS = [
    # ... existing apps
    'django_prometheus',
]

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    # ... existing middleware
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

# Prometheus metrics endpoint
PROMETHEUS_EXPORT_MIGRATIONS = True
```

**Step 2: Install Prometheus & Grafana**
```bash
# Using Docker Compose (add to docker-compose.yml):

prometheus:
  image: prom/prometheus:latest
  container_name: prometheus
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  ports:
    - "9090:9090"
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'

grafana:
  image: grafana/grafana:latest
  container_name: grafana
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
  ports:
    - "3000:3000"
  volumes:
    - grafana_data:/var/lib/grafana
  depends_on:
    - prometheus

volumes:
  prometheus_data:
  grafana_data:
```

**File: `prometheus.yml`**
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'helperlearner'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

**Step 3: Access Dashboards (Once Running)**
```bash
# Prometheus metrics explorer
http://localhost:9090

# Grafana dashboard
http://localhost:3000
# Login: admin / admin
```

**Step 4: Create Grafana Dashboard**
- Go to Grafana → Create Dashboard → Add Panel
- Query Prometheus metrics:
  ```
  django_http_requests_total
  django_http_requests_latency_seconds_by_view_method_bucket
  ```
- Visualize: Response time, Error rate, Request count

**Free Tools Used:** Prometheus, Grafana (open-source, self-hosted)

---

#### 7.6 Security in CI/CD Pipeline

**Best Practice: Secret Management**
```yaml
# In .github/workflows/ci-cd.yml

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      # ✅ Correct: Use GitHub Secrets
      - name: Deploy with secrets
        env:
          SECRET_KEY: ${{ secrets.DJANGO_SECRET_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          echo "Deploying with secrets (not printed for security)"
```

**How to Add Secrets in GitHub:**
1. Go to your repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add `DJANGO_SECRET_KEY`, `DATABASE_URL`, etc.
4. Reference in workflows using `${{ secrets.SECRET_NAME }}`

**Best Practice: Branch Protection & Status Checks**
```bash
# CLI commands to enforce standards
git push origin main

# GitHub will automatically:
# 1. Run tests
# 2. Build Docker image
# 3. Check coverage threshold
# 4. Only allow merge if all checks pass
```

**Free Tools Used:** GitHub Secrets (built-in)

---

### Summary: Free Implementation Checklist

| Concept | Tool | Cost | Status |
|---------|------|------|--------|
| **Version Control** | GitHub | Free | ✅ Implemented |
| **Containerization** | Docker Desktop | Free | 🔄 To Implement |
| **Container Orchestration** | Docker Compose | Free | 🔄 To Implement |
| **CI/CD Pipeline** | GitHub Actions | Free (2000 min/mo) | 🔄 To Implement |
| **Infrastructure as Code** | Docker Compose + YAML | Free | 🔄 To Implement |
| **Monitoring** | Prometheus + Grafana | Free (Self-hosted) | 🔄 To Implement |
| **Secrets Management** | GitHub Secrets | Free (Built-in) | 🔄 To Implement |
| **Cloud Deployment** | AWS Free Tier | Free (750 hrs/mo) | Optional |

---

## 8. Viva Preparation (Top Questions)

1.  **Q: Difference between VM and Container?**
    *   *A:* VMs have their own Guest OS (Heavy). Containers share the Host OS Kernel (Light/Fast).
2.  **Q: What is "Self-Healing" in your project?**
    *   *A:* My Kubernetes deployment uses **Liveness Probes**. If the app crashes, K8s detects it and restarts the pod automatically.
3.  **Q: What is the benefit of Terraform?**
    *   *A:* It prevents "Configuration Drift" and allows us to create 100 servers with one command.
4.  **Q: Why use a Multi-stage Docker build?**
    *   *A:* To separate the "build tools" from the "running app." It makes the final image smaller and more secure.

---

## 8. Viva Preparation (Top Questions)

1.  **Q: Difference between VM and Container?**
    *   *A:* VMs have their own Guest OS (Heavy). Containers share the Host OS Kernel (Light/Fast).
2.  **Q: What is "Self-Healing" in your project?**
    *   *A:* My Kubernetes deployment uses **Liveness Probes**. If the app crashes, K8s detects it and restarts the pod automatically.
3.  **Q: What is the benefit of Terraform?**
    *   *A:* It prevents "Configuration Drift" and allows us to create 100 servers with one command.
4.  **Q: Why use a Multi-stage Docker build?**
    *   *A:* To separate the "build tools" from the "running app." It makes the final image smaller and more secure.
5.  **Q: How do you apply DevOps to YOUR project?**
    *   *A:* I use GitHub Actions for CI/CD, Docker for containerization, docker-compose as IaC, and Prometheus+Grafana for monitoring. Everything is automated and runs for free.

---

## 9. Summary Checklist for Demo

### Phase 1: Containerization (Week 1)
- [ ] **Dockerfile:** Create multi-stage Dockerfile for Django app
- [ ] **Test Locally:** Run `docker build` and `docker run` successfully
- [ ] **Docker Compose:** Create `docker-compose.yml` with web + database services
- [ ] **Git Commit:** `git push` with "feat(docker): Add containerization"`

### Phase 2: CI/CD Pipeline (Week 2)
- [ ] **GitHub Actions:** Create `.github/workflows/ci-cd.yml`
- [ ] **Auto Tests:** Push code → Pipeline runs tests automatically
- [ ] **Build Image:** Pipeline builds Docker image on success
- [ ] **Security:** Add GitHub Secrets for sensitive data

### Phase 3: Monitoring (Week 3)
- [ ] **Prometheus + Grafana:** Add to docker-compose.yml
- [ ] **Django Metrics:** Install `django-prometheus` 
- [ ] **Dashboard:** Create Grafana dashboard showing CPU/Memory/Requests
- [ ] **Health Checks:** Implement health endpoint `/health`

### Phase 4: Documentation & Demo
- [ ] **README Update:** Document how to run with Docker Compose
- [ ] **Demo Flow:** 
  1. Show git commits following DevOps patterns
  2. Push to GitHub → Watch GitHub Actions run tests + build
  3. Show Prometheus metrics
  4. Show Grafana dashboard
- [ ] **Viva Preparation:** Be ready to explain IaC, CI/CD, monitoring concepts

---

## 10. Free Resources & Links

- **Docker Documentation:** https://docs.docker.com/
- **GitHub Actions Guide:** https://docs.github.com/en/actions
- **Prometheus:** https://prometheus.io/docs/
- **Grafana:** https://grafana.com/docs/
- **Django Prometheus:** https://github.com/korfuri/django-prometheus
- **AWS Free Tier:** https://aws.amazon.com/free/

---

Prepared for: INT377 Student Submission
Status: Comprehensive DevOps Implementation Guide (All Units I-V with free tools)
Last Updated: 2026-05-15
