# INT377: DevOps Transformation Guide for HelperLearner
## "Automation, Monitoring, and Self-Healing"
### Final Submission & Study Master Plan (Units I-V)

---

## 0. Prerequisites

Install these tools before starting:

| Tool | Purpose | Install From | Required For |
|------|---------|--------------|-------------|
| **Git** | Version control | https://git-scm.com/ | All phases |
| **Docker Desktop** | Containerization | https://www.docker.com/products/docker-desktop/ | Phase 1+ |
| **Python 3.12** | Django runtime | https://www.python.org/downloads/ | All phases |
| **VS Code** | Code editor | https://code.visualstudio.com/ | All phases |
| **Minikube** | Local Kubernetes | https://minikube.sigs.k8s.io/docs/start/ | Phase 3 |
| **kubectl** | K8s CLI | Installed with Minikube | Phase 3 |
| **AWS CLI** | Cloud management | https://aws.amazon.com/cli/ | Phase 4 |
| **AWS Account** | Free tier access | https://aws.amazon.com/free/ | Phase 4 |

**Verify installations:**
```bash
git --version            # 2.x+
docker --version         # 24.x+
python --version         # 3.12.x
minikube version         # v1.x+
kubectl version --client # v1.x+
aws --version            # aws-cli/2.x+
```

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

## 1.5 Quick Start: Run HelperLearner Locally in 5 Minutes

**Goal:** See the complete DevOps setup running on your laptop before diving into cloud.

```bash
# Step 1: Clone and navigate (30 seconds)
git clone https://github.com/savinaysingh7/HelperLearner.git
cd HelperLearner

# Step 2: Start with Docker Compose (2 minutes)
docker-compose up -d

# Step 3: Verify everything works (2 minutes)
docker-compose ps                    # See running containers
curl http://localhost:8000           # Test Django app
curl http://localhost:9090           # Prometheus metrics
# Open http://localhost:3000 in browser for Grafana

# Step 4: View logs if needed
docker-compose logs -f web
```

**That's it!** You now have:
- ✅ Django app running
- ✅ PostgreSQL database
- ✅ Prometheus metrics
- ✅ Grafana dashboard
- ✅ All for $0 (local development)

**Next:** Commit to GitHub → GitHub Actions tests automatically → Push to AWS EC2 (optional)

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
cd HelperLearner   # Navigate to your project root directory

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

### From Unit II: Container Orchestration with Kubernetes
**Applied Concepts:** Container Orchestration, Self-Healing, Pod Management

#### 7.4 Kubernetes Orchestration (Minikube Local Setup)

**Concept:** Kubernetes is an "orchestrator" that manages containers across multiple machines. It provides:
- **Self-Healing:** Restarts crashed containers automatically
- **Auto-Scaling:** Adds more containers when load increases
- **Rolling Updates:** Updates containers without downtime

**Step 1: Install Minikube (Local Kubernetes)**
```bash
# Download and install Minikube (Windows/Mac/Linux)
# Go to: https://minikube.sigs.k8s.io/docs/start/

# Verify installation
minikube version
kubectl version --client

# Start Minikube cluster
minikube start --cpus=2 --memory=2048

# Verify cluster is running
kubectl cluster-info
```

**Step 2: Create Kubernetes Manifests for HelperLearner**

**File: `k8s/deployment.yaml`**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: helperlearner-web
  labels:
    app: helperlearner
spec:
  replicas: 3  # Always run 3 copies for resilience
  selector:
    matchLabels:
      app: helperlearner
  template:
    metadata:
      labels:
        app: helperlearner
    spec:
      containers:
      - name: web
        image: helperlearner:latest
        ports:
        - containerPort: 8000
        env:
        - name: DEBUG
          value: "False"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: helperlearner-secrets
              key: database-url
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

**File: `k8s/service.yaml`**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: helperlearner-service
spec:
  type: LoadBalancer
  selector:
    app: helperlearner
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
```

**File: `k8s/secrets.yaml`**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: helperlearner-secrets
type: Opaque
stringData:
  database-url: postgresql://user:password@postgres:5432/helperlearner
```

**Step 3: Deploy to Minikube**
```bash
# Build Docker image locally and load into Minikube
docker build -t helperlearner:latest .
minikube image load helperlearner:latest

# Create secrets
kubectl apply -f k8s/secrets.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Verify deployment
kubectl get pods                           # See running pods
kubectl get services                       # See services
kubectl describe pod <pod-name>           # Detailed pod info
kubectl logs <pod-name>                   # View logs
```

**Step 4: Access the Application**
```bash
# Get Minikube service URL
minikube service helperlearner-service

# Or manually open tunnel
kubectl port-forward svc/helperlearner-service 8000:80
# Now access at http://localhost:8000
```

**Step 5: Self-Healing Demo**
```bash
# Kill a pod - K8s automatically restarts it
kubectl delete pod <pod-name>

# Watch Kubernetes create a new pod to maintain 3 replicas
kubectl get pods -w  # Watch mode - shows live updates
```

**Step 6: Scale the Application**
```bash
# Kubernetes makes it easy to scale
kubectl scale deployment helperlearner-web --replicas=5

# View all 5 pods running
kubectl get pods

# Scale back down
kubectl scale deployment helperlearner-web --replicas=3
```

**Key Kubernetes Concepts (For Viva):**
- **Pod:** Smallest unit (one or more containers)
- **Deployment:** Manages pod replicas, ensures desired state
- **Service:** Provides network access to pods (load balancer)
- **ConfigMap:** Stores non-secret configuration
- **Secret:** Stores sensitive data (passwords, API keys)
- **Liveness Probe:** Checks if container is alive, restarts if fails
- **Readiness Probe:** Checks if container is ready to accept traffic

**Cost:** Minikube on laptop = **$0** ✅

**Production Note:** For AWS, use **Amazon EKS** (Elastic Kubernetes Service) - managed Kubernetes with free tier

---

### From Unit IV: CI/CD Pipelines
**Applied Concepts:** Continuous Integration, Automated Testing & Deployment

#### 7.5 GitHub Actions CI/CD Pipeline (FREE!)

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

#### 7.6 Monitoring Stack with Prometheus & Grafana (FREE)

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

#### 7.7 Security in CI/CD Pipeline

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

### From Unit III: Cloud Services (AWS)
**Applied Concepts:** AWS EC2, Cloud Economics, Free Tier Strategy

#### 7.8 AWS EC2 Deployment (FREE Tier - 750 hours/month)

**Step 1: Set Up AWS Billing Alarms (CRITICAL - Do this FIRST!)**
```bash
# Log into AWS Console → CloudWatch → Alarms → Billing
# 1. Create alarm for when bill exceeds $0.10 (₹8)
# 2. Set notification to your email
# This prevents accidental charges
```

**Step 2: Create EC2 Instance**
```bash
# AWS Console → EC2 → Launch Instance
# Select:
#   - AMI: Ubuntu 22.04 LTS (Free Tier eligible)
#   - Instance Type: t2.micro (Free Tier)
#   - Storage: 30 GB (Free Tier includes 30 GB/month)
#   - Security Group: Allow SSH (port 22), HTTP (80), HTTPS (443), Custom TCP 8000
# Download key pair (.pem file) - store safely!
```

**Step 3: Connect to EC2 Instance**
```bash
# Replace <your-instance-ip> with actual EC2 public IP
ssh -i "your-key.pem" ubuntu@<your-instance-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installations
docker --version
docker-compose --version
```

**Step 4: Deploy Your App on EC2**
```bash
# Clone your GitHub repository on EC2
git clone https://github.com/savinaysingh7/HelperLearner.git
cd HelperLearner

# Create .env file with production settings
cat > .env << EOF
DEBUG=False
ALLOWED_HOSTS=<your-instance-ip>,localhost
SECRET_KEY=your-production-secret-key-here
DATABASE_URL=postgresql://user:password@db:5432/helperlearner
EOF

# Start with docker-compose
docker-compose up -d

# Verify services
docker-compose ps
curl http://localhost:8000

# View logs
docker-compose logs -f web
```

**Step 5: Configure Nginx Reverse Proxy (Optional but Recommended)**
```bash
# Install Nginx
sudo apt install nginx -y

# Create Nginx config
sudo tee /etc/nginx/sites-available/helperlearner > /dev/null << EOF
server {
    listen 80;
    server_name <your-instance-ip>;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /metrics {
        proxy_pass http://localhost:9090;
    }

    location /grafana {
        proxy_pass http://localhost:3000;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/helperlearner /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

**Step 6: Enable Auto-Start on EC2 Reboot**
```bash
# Create systemd service for docker-compose
sudo tee /etc/systemd/system/helperlearner.service > /dev/null << EOF
[Unit]
Description=HelperLearner Docker Compose
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/HelperLearner
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=ubuntu

[Install]
WantedBy=multi-user.target
EOF

# Enable auto-start
sudo systemctl enable helperlearner.service
```

**Cost Calculation:**
- t2.micro instance: **FREE** (750 hours/month)
- Storage (30 GB): **FREE** (included in Free Tier)
- Data transfer OUT: **FREE** (1 GB/month free)
- **Total: $0** ✅

---

#### 7.9 GitHub Actions → AWS EC2 Auto-Deploy Pipeline

**Update: `.github/workflows/ci-cd.yml` - Add deployment stage**

```yaml
name: HelperLearner CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    # ... (same as before)

  build:
    # ... (same as before)

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to AWS EC2
      uses: appleboy/ssh-action@master
      with:
        host: ${{ secrets.AWS_EC2_HOST }}
        username: ubuntu
        key: ${{ secrets.AWS_EC2_KEY }}
        script: |
          cd ~/HelperLearner
          git pull origin main
          docker-compose pull
          docker-compose up -d --force-recreate
          docker-compose exec -T web python manage.py migrate
          echo "✅ Deployment successful!"
    
    - name: Slack Notification
      uses: slackapi/slack-github-action@v1.24.0
      with:
        payload: |
          {
            "text": "✅ HelperLearner deployed to AWS EC2",
            "blocks": [
              {
                "type": "section",
                "text": {
                  "type": "mrkdwn",
                  "text": "Deployment to AWS EC2\nBranch: main\nApp: http://${{ secrets.AWS_EC2_HOST }}"
                }
              }
            ]
          }
      env:
        SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

**GitHub Secrets to Add:**
1. `AWS_EC2_HOST` - Your EC2 instance public IP
2. `AWS_EC2_KEY` - Content of your .pem private key
3. `SLACK_WEBHOOK_URL` - (Optional) For notifications

**Workflow:**
```
Push to main → GitHub Actions Tests Pass → Build Docker Image → Auto-Deploy to EC2
```

---

#### 7.10 AWS Deployment Comparison (Choose Your Path)

**Our Recommendation: EC2 (You just completed this above)**

Why EC2 for learning DevOps?
- Full control over infrastructure
- Learn shell commands, networking, security groups
- Understand how CI/CD deploys to real servers
- Perfect for viva demonstration

**Alternative Options (For Reference):**

| Aspect | EC2 | Elastic Beanstalk | Lambda |
|--------|-----|-------------------|--------|
| **Free Tier** | 750 hrs/mo t2.micro ✅ | Included (free tier EC2) | 1M requests/mo |
| **Best For** | Always-on web apps | Managed deployment | Event-driven functions |
| **Learning Value** | ⭐⭐⭐⭐⭐ DevOps | ⭐⭐⭐ Abstracted | ⭐⭐ Serverless |
| **Setup Complexity** | Medium | Easy | Medium |
| **Cold Starts** | None | None | Yes (cold start delays) |
| **Django Friendly** | Perfect | Good | Not ideal |
| **Effort to Deploy** | 30 min (one-time) | 5 min (easy) | 20 min (Zappa setup) |

**For Your Project:** Use **EC2** (already covered above). If curious about others, they're easy to explore after mastering EC2.

---

#### 7.11 Real DevOps Flow (From Laptop to AWS EC2)

```
┌─────────────────────────────────────────────────────────────┐
│  Developer's Laptop (Local Development)                     │
│  ├─ Edit code in VS Code                                    │
│  ├─ Test with docker-compose up                             │
│  └─ git push origin feature/new-feature                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  GitHub Repository                                          │
│  └─ Webhook triggers GitHub Actions                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  GitHub Actions CI/CD Pipeline                              │
│  ├─ Stage 1: Run pytest                                     │
│  ├─ Stage 2: Build Docker image                             │
│  └─ Stage 3: If main branch → Deploy to EC2                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  AWS EC2 Instance (t2.micro - FREE)                         │
│  ├─ SSH into instance                                       │
│  ├─ Pull latest code                                        │
│  ├─ Run migrations                                          │
│  ├─ Restart docker-compose                                  │
│  └─ Django app live at http://<public-ip>                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Monitoring (Prometheus + Grafana)                          │
│  ├─ Scrape metrics from app                                 │
│  ├─ Display on Grafana dashboard                            │
│  └─ Alert if CPU > 80%                                      │
└─────────────────────────────────────────────────────────────┘
```

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

## 7.12 Troubleshooting & Common Issues

### Docker Issues

**Problem: `docker: command not found`**
- **Solution:** Docker not installed. Download from https://www.docker.com/products/docker-desktop/
- **Verification:** Run `docker --version`

**Problem: Port 8000 already in use**
```bash
# Find what's using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or use different port
docker run -p 8001:8000 helperlearner:latest
```

**Problem: Docker image too large**
```bash
# Use multi-stage build (already in Dockerfile)
# Or remove unnecessary files from .dockerignore
# Check size:
docker images | grep helperlearner
```

### GitHub Actions Issues

**Problem: CI/CD pipeline fails**
1. Go to your repo → Actions tab
2. Click the failed workflow → See error details
3. Common causes:
   - Missing dependencies: Add to `requirements.txt`
   - Database connection: Check `DATABASE_URL` in secrets
   - Test failures: Run locally with `pytest` first

**Problem: Secrets not working**
```bash
# Secrets must be added in GitHub Settings
# Go to: Settings → Secrets and variables → Actions
# Reference as: ${{ secrets.SECRET_NAME }}
```

### AWS EC2 Issues

**Problem: Can't SSH into EC2**
```bash
# Verify:
1. Key pair (.pem file) has correct permissions: chmod 400 key.pem
2. Security Group allows SSH (port 22)
3. Correct username for AMI (ubuntu for Ubuntu, ec2-user for Amazon Linux)

# Try:
ssh -i "key.pem" ubuntu@<public-ip> -v  # -v shows details
```

**Problem: App not accessible at public IP**
```bash
# Check if container is running
docker ps

# Check logs
docker-compose logs -f web

# Verify port mapping
docker port helperlearner_web

# Temporarily allow all traffic (for debugging only)
# In Security Group: Add rule allowing all traffic
```

**Problem: Out of AWS free tier**
```bash
# Immediately stop EC2 instance
# AWS Console → EC2 → Instances → Stop
# This prevents charges
# Check billing: AWS Console → Billing Dashboard
```

### Kubernetes (Minikube) Issues

**Problem: `minikube start` fails**
```bash
# Ensure virtualization is enabled in BIOS
# Delete and restart cluster
minikube delete
minikube start --cpus=2 --memory=2048
```

**Problem: Pod stuck in `CrashLoopBackOff`**
```bash
# Check logs
kubectl logs <pod-name>

# Describe pod for details
kubectl describe pod <pod-name>

# Common cause: Application crashed (check health endpoint)
```

### Monitoring Issues

**Problem: Prometheus can't scrape metrics**
```bash
# Check if Django app is running
curl http://localhost:8000/metrics

# Verify prometheus.yml target is correct
# Default: localhost:8000

# If using Docker, use service name instead of localhost
targets: ['web:8000']  # web is service name in docker-compose
```

**Problem: Grafana dashboard not showing data**
1. Wait 1-2 minutes for Prometheus to scrape metrics
2. In Grafana, verify Prometheus datasource is configured
3. Go to Prometheus web UI and check targets status

### General Debugging Tips

1. **Read logs carefully**
   ```bash
   docker-compose logs web      # Recent logs
   docker-compose logs -f web   # Follow logs in real-time
   ```

2. **Test incrementally**
   - Test locally with docker-compose before pushing to AWS
   - Test on one container before scaling to multiple replicas

3. **Use health checks**
   ```bash
   curl http://localhost:8000/health  # Should return 200 OK
   ```

4. **Environment variables**
   - For local: Check `.env` file
   - For AWS: Check GitHub Secrets
   - For Kubernetes: Check `secrets.yaml`

---

## 8. Viva Preparation (Top Questions)

### Unit I & II: Cloud & Containerization

1.  **Q: Difference between VM and Container?**
    *   *A:* VMs have their own Guest OS (Heavy ~1-2 GB). Containers share the Host OS Kernel (Light ~50-200 MB). Containers are faster to start and more resource-efficient.

2.  **Q: What is IaC and why use it?**
    *   *A:* Infrastructure as Code means describing infrastructure (servers, databases, networks) in code (YAML, HCL) instead of clicking AWS console. Benefits: Reproducibility, version control, automation, disaster recovery.

3.  **Q: Explain your Docker setup**
    *   *A:* I use a multi-stage Dockerfile to keep the final image small. Stage 1 builds dependencies, Stage 2 runs the app. Docker Compose orchestrates web + database locally.

### Unit II: Container Orchestration (Kubernetes)

4.  **Q: What is Kubernetes and what does it solve?**
    *   *A:* Kubernetes is a container orchestrator that manages thousands of containers across multiple servers. It provides:
        - **Auto-healing:** Restarts crashed containers automatically
        - **Auto-scaling:** Adds more containers under high load
        - **Rolling updates:** Updates without downtime
        - **Self-service deployment:** Developers deploy without ops teams

5.  **Q: What is "Self-Healing" in your project?**
    *   *A:* My Kubernetes deployment uses **Liveness Probes** (health checks). If the app crashes, K8s detects it within 10 seconds and automatically restarts the pod. This is like having a 24/7 ops engineer watching your app.

6.  **Q: Explain Pods, Deployments, and Services**
    *   *A:* 
        - **Pod:** Smallest unit (one or more containers). Usually one app per pod.
        - **Deployment:** Manages multiple pod replicas. Ensures 3 copies always running. If one dies, it creates a new one.
        - **Service:** Load balancer that distributes traffic across pods. Hides pod complexity from users.

7.  **Q: What are probes and why needed?**
    *   *A:* Probes are health checks:
        - **Liveness Probe:** "Is the app alive?" If fails, restart pod.
        - **Readiness Probe:** "Is the app ready to serve?" If fails, don't send traffic.
        - Essential for reliability. My health endpoint: `GET /health → 200 OK`

### Unit III: Infrastructure as Code

8.  **Q: What is the benefit of Terraform/IaC?**
    *   *A:* It prevents "Configuration Drift" (manual changes that make servers different). With IaC:
        - One command creates 100 servers identically
        - Changes are tracked in git (audit trail)
        - Disaster recovery is fast (redeploy infrastructure from code)
        - My project uses Docker Compose as IaC for database configuration

9.  **Q: How do you manage secrets (passwords, API keys)?**
    *   *A:* Never hardcode secrets! My approach:
        - **Local dev:** .env files (git-ignored)
        - **GitHub Actions:** GitHub Secrets (encrypted)
        - **Kubernetes:** K8s Secrets (encrypted at rest)
        - Reference as environment variables in code

### Unit IV: CI/CD

10. **Q: Explain your CI/CD pipeline**
    *   *A:* My GitHub Actions workflow:
        1. **Trigger:** Push to main branch
        2. **Test:** Run pytest (automated tests)
        3. **Build:** Create Docker image
        4. **Deploy:** SSH into AWS EC2 and run `docker-compose up`
        - Entire flow: code → test → build → deploy (5 minutes)

11. **Q: What is continuous integration vs. continuous deployment?**
    *   *A:*
        - **CI (Continuous Integration):** Automatically test every code change. My GitHub Actions runs tests on each push.
        - **CD (Continuous Deployment):** Automatically deploy to production after tests pass. My workflow does this to AWS EC2.
        - Benefits: Catch bugs early, deploy multiple times per day, confidence in releases

### Unit V: Monitoring & Security

12. **Q: How do you monitor your app?**
    *   *A:* I use **Prometheus + Grafana**:
        - **Prometheus:** Collects metrics (requests/sec, latency, errors)
        - **Grafana:** Visualizes dashboards (graphs, alerts)
        - **Django Prometheus:** Middleware that exports metrics
        - **Health endpoint:** `/health` checks if app is responsive
        - Alert if response time > 500ms

13. **Q: What is the Shared Responsibility Model?**
    *   *A:*
        - **Cloud Provider (AWS):** Responsible for **security OF the cloud** (hardware, data centers, networking)
        - **Us:** Responsible for **security IN the cloud** (our app, secrets, access control, firewalls)
        - We must patch our code, manage passwords, configure firewalls

14. **Q: How do you protect against security vulnerabilities?**
    *   *A:* My approach:
        - **Code:** Use Django's built-in CSRF protection, parameterized queries
        - **Secrets:** GitHub Secrets for API keys (never in code)
        - **CI/CD:** GitHub Actions checks code before merging
        - **Access:** IAM least privilege (minimum permissions needed)
        - **Monitoring:** Prometheus alerts if suspicious patterns

### Why You're Awesome at DevOps (Final Answer)

15. **Q: How do you apply ALL units of this syllabus to YOUR project?**
    *   *A:* My HelperLearner project demonstrates complete DevOps:
        - **Unit I (Cloud):** Using AWS Public Cloud (EC2), Git with GitHub
        - **Unit II (Containerization):** Docker for app, Kubernetes for orchestration
        - **Unit III (IaC):** Docker Compose + K8s YAML
        - **Unit IV (CI/CD):** GitHub Actions automated pipeline (test → build → deploy)
        - **Unit V (Monitoring):** Prometheus metrics + Grafana dashboards + Security best practices
        - **Cost:** Everything runs on **free tier** ($0)
        - **Flow:** Push code → Automated tests → Automatic deployment → Monitoring dashboard

### Demo Walkthrough Script (Use During Viva — ~12 Minutes)

Follow this exact sequence during your demo:

**Minute 0–2: Architecture Overview**
- Open this master plan → show the DevOps flow diagram (Section 7.11)
- Explain: *"Code → GitHub → CI/CD → Docker → Kubernetes → Monitoring — all free tier"*

**Minute 2–4: Git & CI/CD Demo**
```bash
# Show DevOps-style commit history
git log --oneline -10

# Make a small change to trigger the pipeline
echo "# Demo update" >> README.md
git add . && git commit -m "ci: demo commit to trigger pipeline"
git push origin main

# Open browser → GitHub repo → Actions tab → watch pipeline run
# URL: https://github.com/savinaysingh7/HelperLearner/actions
```

**Minute 4–6: Docker & Containerization Demo**
```bash
cat Dockerfile                        # Show the Dockerfile
docker build -t helperlearner:demo .   # Build image
docker images | grep helperlearner     # Show image size
docker-compose up -d                   # Start full stack
docker-compose ps                      # Show all services running
```

**Minute 6–8: Kubernetes Self-Healing Demo**
```bash
kubectl get pods                       # Show running pods
kubectl delete pod <pod-name>          # Kill a pod
kubectl get pods -w                    # Watch K8s auto-restart it

# Scale up and back down
kubectl scale deployment helperlearner-web --replicas=5
kubectl get pods                       # Show 5 pods
kubectl scale deployment helperlearner-web --replicas=3
```

**Minute 8–10: Monitoring Demo**
```bash
# Open Prometheus: http://localhost:9090
# → Show targets are healthy
# → Query: django_http_requests_total

# Open Grafana: http://localhost:3000
# → Show dashboard with request count, latency, errors
```

**Minute 10–12: Wrap-Up**
- Show AWS EC2 running (if deployed): `http://<your-ec2-ip>`
- Show GitHub Secrets page (Settings → Secrets → don't reveal values!)
- Summarize: *"All 5 syllabus units covered — Git, Docker, K8s, CI/CD, Monitoring — total cost: $0"*

**If live demo fails:** Show screenshots and walk through this master plan. All configurations are documented here.

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

### Phase 3: Kubernetes Orchestration (Week 3) ⭐ NEW
- [ ] **Minikube:** Install and verify local Kubernetes cluster
- [ ] **K8s Manifests:** Create deployment.yaml, service.yaml, secrets.yaml
- [ ] **Deploy:** Apply manifests to Minikube cluster
- [ ] **Test:** Verify self-healing (delete pod, watch restart)
- [ ] **Scale:** Test scaling up/down replicas

### Phase 4: AWS EC2 Deployment (Week 4)
- [ ] **AWS Account:** Sign up for AWS Free Tier (if not done)
- [ ] **Billing Alarm:** Set CloudWatch alert for $0.10 threshold
- [ ] **EC2 Instance:** Launch t2.micro Ubuntu instance
- [ ] **Docker Setup:** Install Docker & Docker Compose on EC2
- [ ] **Deploy App:** Push code → GitHub Actions auto-deploys to EC2
- [ ] **Nginx Setup:** Configure reverse proxy (optional but recommended)
- [ ] **Auto-Start:** Create systemd service for docker-compose
- [ ] **Test:** Verify app runs at http://<your-ec2-ip>

### Phase 5: Monitoring (Week 5)
- [ ] **Prometheus + Grafana:** Add to docker-compose.yml on EC2
- [ ] **Django Metrics:** Install `django-prometheus` 
- [ ] **Dashboard:** Create Grafana dashboard showing CPU/Memory/Requests
- [ ] **Health Checks:** Implement health endpoint `/health`
- [ ] **Access:** Verify Grafana at http://<your-ec2-ip>/grafana

### Phase 6: Documentation & Demo
- [ ] **README Update:** Document how to run with Docker Compose locally and deploy to AWS
- [ ] **Architecture Diagram:** Show GitHub → Actions → EC2 → Monitoring flow
- [ ] **Cost Analysis:** Explain AWS Free Tier savings ($0 for this setup)
- [ ] **Demo Flow:** 
  1. Show git commits following DevOps patterns
  2. Push to GitHub → Watch GitHub Actions run tests + build + deploy
  3. Access app at AWS EC2 public IP
  4. Show Prometheus metrics
  5. Show Grafana dashboard
  6. Demo Kubernetes locally (if time permits)
- [ ] **Viva Preparation:** Be ready to explain all 15 questions above
- [ ] **Record Demo Video:** (Optional) Show complete workflow for submission

---

## 10. Free Resources & Links

- **Docker Documentation:** https://docs.docker.com/
- **GitHub Actions Guide:** https://docs.github.com/en/actions
- **Kubernetes Official:** https://kubernetes.io/docs/
- **Minikube Setup:** https://minikube.sigs.k8s.io/docs/start/
- **Prometheus:** https://prometheus.io/docs/
- **Grafana:** https://grafana.com/docs/
- **Django Prometheus:** https://github.com/korfuri/django-prometheus
- **AWS Free Tier:** https://aws.amazon.com/free/
- **AWS EC2 Best Practices:** https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/

---

## 11. Final Summary

### What You've Built

Your HelperLearner project now demonstrates **complete DevOps mastery:**

| Component | Technology | Cost | Status |
|-----------|-----------|------|--------|
| Version Control | GitHub | Free | ✅ |
| Containerization | Docker | Free | ✅ |
| Local Orchestration | Docker Compose | Free | ✅ |
| Container Orchestration | Kubernetes (Minikube) | Free | ✅ |
| CI/CD Pipeline | GitHub Actions | Free | ✅ |
| Cloud Deployment | AWS EC2 | Free Tier | ✅ |
| Monitoring | Prometheus + Grafana | Free | ✅ |
| Security | GitHub Secrets + IAM | Free | ✅ |
| **Total Cost** | **ALL FREE** | **$0** | ✅ |

### Key Achievements

1. **Unit I - Cloud Computing:**
   - ✅ Understood IaaS, PaaS, SaaS models
   - ✅ Used GitHub (SaaS), AWS (IaaS), Nginx (Infrastructure)
   - ✅ Git workflow with branches and CI/CD integration

2. **Unit II - Containerization & Orchestration:**
   - ✅ Created optimized multi-stage Dockerfile
   - ✅ Docker Compose for local development
   - ✅ Kubernetes for production-ready orchestration
   - ✅ Implemented self-healing with liveness probes

3. **Unit III - Infrastructure as Code:**
   - ✅ Docker Compose as IaC for reproducible deployments
   - ✅ Kubernetes YAML for declarative infrastructure
   - ✅ Secrets management across environments
   - ✅ Cost optimization within free tier limits

4. **Unit IV - CI/CD Automation:**
   - ✅ GitHub Actions pipeline (test → build → deploy)
   - ✅ Automated testing on every push
   - ✅ Automated Docker image building
   - ✅ Automated deployment to AWS EC2

5. **Unit V - Monitoring & Security:**
   - ✅ Prometheus metrics collection
   - ✅ Grafana dashboards for visualization
   - ✅ Health check endpoints for monitoring
   - ✅ GitHub Secrets for sensitive data
   - ✅ Shared responsibility model understanding
   - ✅ Security best practices in CI/CD

### Viva Readiness Checklist

- [ ] Understand all 15 viva questions (Section 8)
- [ ] Explain the complete DevOps flow (local → GitHub → AWS)
- [ ] Describe self-healing and how Kubernetes prevents downtime
- [ ] Explain cost savings (all free tier = $0)
- [ ] Demo pushing code → watching CI/CD run → seeing deployment on AWS
- [ ] Show Prometheus metrics and Grafana dashboard
- [ ] Discuss trade-offs (EC2 vs Lambda vs Elastic Beanstalk)
- [ ] Explain how your project covers all 5 units of the syllabus

### Implementation Path (6 Weeks)

**Week 1:** Containerization (Docker + Docker Compose)
**Week 2:** CI/CD Pipeline (GitHub Actions)
**Week 3:** Kubernetes Orchestration (Minikube local)
**Week 4:** AWS EC2 Deployment
**Week 5:** Monitoring & Observability
**Week 6:** Documentation & Viva Preparation

---

Prepared for: INT377 Final Submission
Status: **COMPREHENSIVE DevOps Guide - All Units I-V with FREE Implementation**
Total Lines: 1500+ lines of guide + code examples
Last Updated: 2026-05-16
Version: 2.1 (Added Prerequisites, Demo Script, Fixed Section Numbering)
