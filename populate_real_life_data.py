import os
import sys
import django
from datetime import timedelta
from django.utils import timezone
import random

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helperlearner_root.settings.dev")
django.setup()

from marketplace.models import HelpRequest, FreelanceJob, Skill, Tag
from accounts.models import CustomUser

def run():
    print("Populating database with highly realistic Indian dev data...")
    
    # Get random users
    users = list(CustomUser.objects.all())
    if not users:
        print("No users found. Please run the original seed first.")
        return
        
    skills = list(Skill.objects.all())
    tags = list(Tag.objects.all())
    now = timezone.now()
    
    # 1. Realistic Help Requests (Hinglish, specific Indian contexts, conversational)
    realistic_requests = [
        {
            "title": "Bhai, Razorpay webhook failing randomly with signature mismatch",
            "description": "Production pe issue aa raha hai. Razorpay se payment success ho jata hai, but hamara webhook listener signature verification fail kar deta hai. Sirf 10% transactions me ho raha hai. Maybe unicode ya escaping ka panga hai python requests me? Urgent help chahiye yaar, boss gussa kar raha hai.",
            "skill": "Python",
            "kp": 60,
            "tags": ["api", "payments", "backend"]
        },
        {
            "title": "OTP SMS delayed in Gupshup/MSG91 integration. Best fallback?",
            "description": "Hum MSG91 use kar rahe OTPs ke liye, but evening peak hours me messages delay ho rahe hain. Users drop off ho rahe hain signup se. Kya hum WhatsApp API fallback laga sakte hain easily? Koi achha solution batao bhai log jo budget friendly bhi ho.",
            "skill": "System Design",
            "kp": 45,
            "tags": ["authentication", "api", "mobile"]
        },
        {
            "title": "Django ORM query for GST report is timing out on 5M rows",
            "description": "Month end aane wala hai aur accounts team ka GST report query timeout maar raha hai. Django ORM aggregate use kar rahe the hum, ab query 30 sec se upar le rahi hai. Need someone to help me write a raw SQL query with proper CTEs and indexing on PostgreSQL. Please help, CA ka dimaag kharab ho rakha hai.",
            "skill": "PostgreSQL",
            "kp": 80,
            "tags": ["database", "performance", "django"]
        },
        {
            "title": "React Native app build failing on iOS with M1/M2 Mac",
            "description": "CocoaPods issue aa raha hai ffi gem related. 'arch -x86_64 pod install' bhi try kar liya, fir bhi build phase me fatt raha hai. React Native 0.70 hai. Koi M series mac wala bhai ek baar Anydesk/Meet pe aake dekh lo please. 2 din se fasa hu.",
            "skill": "React", # Close enough to React Native
            "kp": 50,
            "tags": ["frontend", "mobile", "debugging"]
        },
        {
            "title": "Jugaad needed: Scraping dynamic content from Swiggy/Zomato for local project",
            "description": "Ek college project ke liye prices compare karne the, but unka DOM completely obfuscated hai aur API Cloudflare se protected hai (403 forbidden). Koi headless browser approach (Puppeteer/Playwright) ka snippet de sakta hai jo stealth mode me chale?",
            "skill": "Node.js",
            "kp": 35,
            "tags": ["api", "data", "testing"]
        }
    ]
    
    for req in realistic_requests:
        skill = next((s for s in skills if s.name.lower() == req["skill"].lower()), skills[0])
        req_tags = [t for t in tags if t.name.lower() in req["tags"]]
        if not req_tags:
            req_tags = [random.choice(tags)]
            
        poster = random.choice(users)
        
        hr = HelpRequest.objects.create(
            title=req["title"],
            description=req["description"],
            user=poster,
            skill_needed=skill,
            kp_bounty=req["kp"],
            status="open",
            created_at=now - timedelta(minutes=random.randint(10, 60))
        )
        hr.tags.set(req_tags)
        hr.save()
        
    print(f"Added {len(realistic_requests)} realistic help requests.")

    # 2. Realistic Freelance Jobs
    realistic_jobs = [
        {
            "title": "Urgent: Complete e-commerce backend in Django (B2B wholesale)",
            "description": "Need a solid backend developer for a B2B wholesale platform. Features include: bulk pricing, GST invoices generation, Razorpay route (split payments for vendors), and basic inventory management. Requirements clearly documented. Budget is fixed at 1.5L. Serious freelancers only.",
            "skill": "Django",
            "budget": 150000.00,
            "timeline": 30,
            "tags": ["django", "backend", "payments"]
        },
        {
            "title": "Migrate old PHP site to Next.js + Node API (SEO focused)",
            "description": "Mera ek purana travel blog hai core PHP pe, usko Next.js pe laana hai kyunki Core Web Vitals kharab ho gaye hain aur traffic gir raha hai. Node.js backend chahiye. URL structure same rehna chahiye taaki 404s na aayein. Budget 45k INR, 2 weeks timeline.",
            "skill": "Next.js",
            "budget": 45000.00,
            "timeline": 14,
            "tags": ["frontend", "api", "seo"] # Assuming SEO tag isn't there, will fallback
        },
        {
            "title": "Fix memory leak in Celery workers (Production issue)",
            "description": "We are processing around 50k background tasks per hour (pdf generation, email alerts). Hamare Celery workers memory kha jate hain and OOM kill ho rahe hain every 4 hours. Max tasks per child aur worker concurrency tweak kiya par theek nahi hua. Need a DevOps/Python expert to profile and fix this. Will pay ₹10,000 for the exact fix.",
            "skill": "DevOps",
            "budget": 10000.00,
            "timeline": 2,
            "tags": ["python", "devops", "performance"]
        }
    ]

    for job in realistic_jobs:
        skill = next((s for s in skills if s.name.lower() == job["skill"].lower()), skills[0])
        job_tags = [t for t in tags if t.name.lower() in job["tags"]]
        if not job_tags:
            job_tags = [random.choice(tags)]
            
        poster = random.choice(users)
        
        fj = FreelanceJob.objects.create(
            title=job["title"],
            description=job["description"],
            client=poster,
            skill_needed=skill,
            budget_inr=job["budget"],
            deadline=now.date() + timedelta(days=job["timeline"]),
            status="open",
            created_at=now - timedelta(minutes=random.randint(60, 120))
        )
        fj.tags.set(job_tags)
        fj.save()
        
    print(f"Added {len(realistic_jobs)} realistic freelance jobs.")
    print("Done! Check the website feed.")

if __name__ == "__main__":
    run()
