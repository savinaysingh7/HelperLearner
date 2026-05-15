# HelperLearner - Live Demo Plan

## Demo Guidelines
* **Duration:** 5-7 minutes.
* **Golden Rule:** Never rely on "waiting for an email" or "waiting for a background task" during a live demo. Have pre-created data ready.
* **Setup Requirements:** Open two different browsers (e.g., Chrome and Edge) or one normal window and one Incognito window to simulate two different users interacting in real-time.

---

## Scenario Pre-requisites (Do this BEFORE the presentation)
1. Ensure the local server (`python manage.py runserver`) and Redis/Celery workers are running.
2. **User A (Requester/Client):** Logged into Chrome. Has at least 500 KP and INR balance.
3. **User B (Helper/Contractor):** Logged into Incognito. High Trust Score, has relevant Python/Django skills on their profile.
4. Have a dummy text file with a "Code Snippet" ready to copy-paste to save typing time.

---

## Step-by-Step Demo Flow

### Phase 1: The Knowledge Marketplace (Help Requests) - *2 mins*

**1. Creating the Request (User A - Chrome)**
*   **Action:** Go to "Create Request".
*   **Input:** Title: "Stuck on Django Channels WebSocket setup", Description: "I keep getting a disconnect error code 1006...", Bounty: 50 KP.
*   **Narration:** *"I'm logged in as a Junior Developer, User A. I'm stuck on a bug, so I'm going to post a Help Request and offer 50 Knowledge Points as a bounty."*

**2. Claiming the Request (User B - Incognito)**
*   **Action:** Switch to Incognito. Refresh the public feed. Click on the new request. Click "Claim Request".
*   **Narration:** *"Switching over to User B, an experienced developer. I see the request on the feed. Since it matches my skills, I will claim it. Notice how the status immediately changes to 'Claimed' so no one else wastes time on it."*

**3. Real-Time Chat & Solution (Both Windows)**
*   **Action:** Open the Chat thread in both windows side-by-side. 
*   **Action:** User B types: "Hey! Let me send you the correct routing.py configuration." User A sees it instantly. User B submits the formal solution.
*   **Narration:** *"Here you can see our WebSocket integration in action. The chat updates instantly without refreshing. User B submits the solution."*

**4. Approval & KP Transfer (User A - Chrome)**
*   **Action:** User A clicks "Approve Solution" and leaves a 5-star rating.
*   **Narration:** *"User A approves it. Watch the wallets—User A's KP is deducted, and User B's KP increases. User B's trust score also gets a positive signal from the 5-star rating."*

---

### Phase 2: The Freelance Escrow Flow - *3 mins*

**1. Viewing a Pre-made Job (User A - Chrome)**
*   **Action:** Navigate to a pre-created Job titled "Build an API for my mobile app".
*   **Narration:** *"Now let's look at the Freelance feature. To save time, I've already created a job posting as User A with a budget of ₹5,000."*

**2. Submitting a Proposal (User B - Incognito)**
*   **Action:** Navigate to the Job. Submit a proposal: Bid: ₹5,000. 
*   **Narration:** *"User B submits a proposal. As a client, User A can review User B's high Trust Score before accepting."*

**3. Funding the Escrow (User A - Chrome)**
*   **Action:** User A clicks "Accept Proposal" and proceeds to the Razorpay mock checkout screen. Completes the test payment.
*   **Narration:** *"User A accepts the proposal. Here is our Razorpay integration. The client funds the milestone, but the money does NOT go to the contractor yet. It is securely locked in our Escrow system."*

**4. Milestone Delivery & Payment Release (Both Windows)**
*   **Action:** Switch to User B. Click "Submit Deliverable" (Upload a dummy file or link).
*   **Action:** Switch to User A. Click "Approve Milestone". 
*   **Action:** Go to User B's Wallet page to show the credited INR balance.
*   **Narration:** *"User B delivers the work. User A reviews and approves it. Now, and only now, the Escrow contract automatically releases the funds to User B's wallet. User B can now withdraw this to their bank."*

---

### Phase 3: Workspaces & AI (Optional / If time permits) - *1 min*

**1. Workspace View (User A - Chrome)**
*   **Action:** Click on the "Workspaces" tab. Open the "Capstone Project" workspace.
*   **Narration:** *"Finally, for larger teams, we have Workspaces. Here you can see our Kanban board where teams can drag and drop issues across sprint stages, keeping everyone aligned."*

**2. AI Moderation (Showcase)**
*   **Action:** Go to the Admin/Moderation panel (or show a flagged request).
*   **Narration:** *"Behind the scenes, we use the Google Gemini API to analyze descriptions for spam or inappropriate content, ensuring the marketplace remains professional."*

---

## Conclusion
*   **Action:** Return to the main dashboard.
*   **Narration:** *"That concludes the core flow of HelperLearner—bridging the gap between peer-to-peer learning and professional freelancing. Thank you!"*
