# README.md Context Explanation

## Why README.md Matters

Your README.md is **crucial** for the hackathon submission because:

1. **First Impression** — Judges read this first to understand what you've built
2. **Documentation** — Describes the problem, solution, and how to use it
3. **HF Spaces Header** — Part of the README becomes the Space's header metadata
4. **Submission Requirement** — Hackathon requires comprehensive documentation

---

## Your README.md Structure (533 lines)

### Section 1: Overview & Motivation (14 lines)
**Why this project matters:**
- Describes real-world SRE challenges at scale companies
- Explains why this is a hard, valuable problem
- Sets context: triage must be fast, under pressure, with incomplete info
- Motivates why a dedicated environment for this is needed

**Key Quote:**
> "No existing OpenEnv environment models this workflow. Yet it is one of the highest-value tasks in the software industry — a well-trained agent here saves real money, reduces MTTR (Mean Time to Recover), and directly impacts user experience."

### Section 2: Environment Description (32 lines)
**What the agent does:**
- Receives live incident feed (batch of logs)
- Takes one action per step
- Episode ends when resolved or step budget exceeded

**Simulated Infrastructure:**
```
[api-gateway] → [auth-service] → [user-db]
             → [payment-service] → [payment-db]
             → [notification-service] → [email-queue]
```

**Log Generation:**
Shows realistic examples:
```
2025-03-25T14:32:01Z ERROR api-gateway [req-id:9f2a] upstream timeout from auth-service: 30002ms
2025-03-25T14:32:02Z WARN  auth-service [req-id:9f2a] db connection pool exhausted (pool=50/50)
2025-03-25T14:32:02Z ERROR user-db       slow query detected: SELECT * FROM sessions WHERE user_id=? [2847ms]
```

### Section 3: Action Space (17 lines)
**7 action types agents can take:**
- `classify_severity` → P1, P2, P3
- `identify_root_cause` → service name
- `escalate` → team name
- `remediate` → restart, rollback, scale, flush-cache, kill-query
- `request_more_logs` → all or specific service
- `resolve` → mark done
- `ignore` → mark as noise

**Table format shows valid values for each.**

### Section 4: Observation Space (35 lines)
**What agent receives each step:**
- Logs (5-15 lines of activity)
- System state (health of each service)
- Incident metadata (ID, task, step count, time)
- Reward signals (immediate + cumulative)
- Feedback on last action
- Error info if action was invalid

**Example LogLine structure shown.**

### Section 5: Reward Function (27 lines)
**Shaped rewards (dense feedback, not sparse):**

Positive rewards:
- Correct severity: +0.30
- Correct root cause: +0.35
- Correct remediation: +0.25
- Escalated correctly: +0.10
- Resolved fast: +0.10
- Partial credit (right family, right tier): +0.10 each

Negative rewards:
- Wrong escalation: -0.10
- Ignore P1: -0.50
- Redundant action: -0.05
- Over-escalate: -0.15
- Exceed step budget: -0.20

**Design rationale:** Partial credit creates learning gradient, speeds bonus encourages efficiency, penalties calibrated to be recoverable.

### Section 6: Tasks & Graders (57 lines)
**Three tasks with increasing difficulty:**

#### Task 1: Single Service Crash (Easy, 8 steps)
- One service clearly broken
- Unambiguous error logs
- Success: P1 → identify → restart
- Expected baseline: 0.75–0.85

#### Task 2: Cascading Failure (Medium, 12 steps)
- Root cause hidden under symptoms
- DB problem → upstream cascade
- Must trace backward to real root
- Expected baseline: 0.45–0.60

#### Task 3: Silent Degradation (Hard, 15 steps)
- Slow creeping problem in 60% noise
- Nuanced P2 judgment (not P1, not P3)
- Requires temporal reasoning
- Expected baseline: 0.20–0.40

**Each includes:**
- Objective (what must be done)
- Scenario (what happens)
- Success criteria (grader scoring)
- Expected baseline score

### Section 7: Episode Boundaries (10 lines)
**When episodes start/end:**
- Start: `reset()` seeds fresh scenario
- End: Agent calls `resolve()`, or step budget exceeded, or ignores non-noise
- State isolation: Each episode fully independent
- Reproducibility: Fixed seed for deterministic replay

### Section 8: API Endpoints (60 lines)
**Three categories:**

**OpenEnv Core:**
- `POST /reset` — Start new episode
- `POST /step` — Take action
- `GET /state` — Current state

**Required Additional:**
- `GET /tasks` — List all 3 tasks
- `POST /grader` — Score after episode
- `POST /baseline` — Run baseline inference

**Health/Meta:**
- `GET /health` — 200 OK
- `GET /openenv.yaml` — Metadata

**Includes JSON response examples for `/tasks`.**

### Section 9: Setup & Installation (23 lines)
**Prerequisites:** Python 3.10+, Docker, HF account

**Local Installation:**
```bash
git clone https://github.com/<username>/logtriage-env
cd logtriage-env
pip install -r server/requirements.txt
openenv validate .
uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

**Baseline:**
```bash
export OPENAI_API_KEY=...
python baseline.py
```

**Validate manually:**
```bash
python scripts/run_grader.py --task single_crash  # (Day 4+)
```

### Section 10: Docker Usage (17 lines)
**Build and run:**
```bash
docker build -t logtriage-env .
docker run -p 7860:7860 logtriage-env
curl http://localhost:7860/health
```

### Section 11: Hugging Face Spaces Deployment (18 lines)
**HF Space configuration:**
- Space URL format
- Docker SDK
- Space header metadata (title, emoji, colorFrom/colorTo, tags)

### Section 12: Baseline Inference Script (45 lines)
**How baseline agent works:**

Pseudocode in Python:
```python
def run_task(task_id: str) -> float:
    obs = requests.post(f"{BASE_URL}/reset", json={"task": task_id})
    
    while not done:
        prompt = build_prompt(obs)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        action = parse_action(response...)
        result = requests.post(f"{BASE_URL}/step", json=action)
        obs = result
        done = result["done"]
    
    score = requests.post(f"{BASE_URL}/grader").json()["score"]
    return score
```

**Shows exactly how agents interact with environment.**

### Section 13: Baseline Scores (9 lines)
**Expected results table (to be filled):**

| Task | Difficulty | Expected Score |
|------|------------|-----------------|
| Single Crash | Easy | 0.75–0.85 |
| Cascading | Medium | 0.45–0.60 |
| Silent Degrade | Hard | 0.20–0.40 |

*"TBD" — filled in after implementation.*

### Section 14: OpenEnv Spec Compliance (15 lines)
**Checklist showing compliance:**
- ✅ Typed Action model
- ✅ Typed Observation model
- ✅ step() → (observation, reward, done, info)
- ✅ reset() → initial obs
- ✅ state() → current state
- ✅ openenv.yaml
- ✅ endpoints
- ✅ Docker
- ✅ HF Space
- ✅ Baseline

### Section 15: Pre-Submission Checklist (14 items)
**What must work before submitting:**
- [ ] openenv validate passes
- [ ] Docker builds
- [ ] Docker runs
- [ ] /health returns 200
- [ ] /reset returns observation
- [ ] /step validates and returns 422 on bad input
- [ ] /tasks returns all 3
- [ ] /grader returns score
- [ ] /baseline completes
- [ ] HF Space responds
- [ ] Baseline script end-to-end
- [ ] Graders vary (not constant)
- [ ] README complete
- [ ] requirements.txt pinned

### Section 16: Project Structure (33 lines)
**Complete folder layout:**
```
logtriage-env/
├── README.md                   ← This file
├── openenv.yaml                ← Spec metadata
├── Dockerfile                  ← Container
├── requirements.txt            ← Dependencies
├── baseline.py                 ← Baseline agent (Day 5)
├── server/
│   ├── app.py                  ← FastAPI app
│   ├── models.py               ← Data models
│   ├── environment.py          ← LogTriageEnvironment (Day 2)
│   ├── log_generator.py        ← Synthetic logs (Day 2)
│   ├── scenarios/
│   │   ├── single_crash.py     ← Task 1 (Day 2)
│   │   ├── cascading.py        ← Task 2 (Day 3)
│   │   └── silent_degrade.py   ← Task 3 (Day 3)
│   └── graders/
│       ├── base_grader.py      ← Base class (Day 4)
│       ├── crash_grader.py     ← Task 1 grader (Day 4)
│       ├── cascade_grader.py   ← Task 2 grader (Day 4)
│       └── noise_grader.py     ← Task 3 grader (Day 4)
└── scripts/
    ├── run_grader.py           ← Manual testing (Day 4)
    └── validate_checklist.py   ← Validation (Day 5)
```

---

## Why This README is Important for Judges

✅ **Clear Problem Statement** — They understand why SRE triage matters  
✅ **Technical Depth** — Shows sophisticated understanding of RL/OpenEnv  
✅ **Reproducibility** — Anyone can clone and run locally  
✅ **Completeness** — Covers everything from high-level to low-level  
✅ **Evidence of Planning** — Shows multi-week development roadmap  
✅ **Professional Presentation** — Well-structured, well-written  

---

## How README Becomes HF Space Header

The first few lines of README.md become your HF Space's header metadata:

```markdown
---
title: LogTriageEnv
emoji: 🚨
colorFrom: red
colorTo: orange
sdk: docker
pinned: false
tags:
  - openenv
  - reinforcement-learning
  - sre
  - log-analysis
---

# LogTriageEnv — OpenEnv Environment
> **Meta × PyTorch Hackathon — Round 1 Submission**
...
```

This displays on HuggingFace with:
- Red→orange gradient
- Alert emoji 🚨
- Tagged with openenv, RL, SRE topics
- Description from first paragraph

---

## What Makes This README Stand Out

1. **Motivation Section** — Explains *why* this matters (real-world value)
2. **Detailed Scenarios** — Concrete examples of what each task looks like
3. **Reward Function Table** — Specific scoring breakdown
4. **API Spec** — Complete endpoint documentation with examples
5. **Testing Instructions** — Copy-paste curl commands
6. **Checklist** — Pre-submission validation guide
7. **File Structure** — Complete project map with file descriptions
8. **Baseline Template** — Shows exactly how agents interact
9. **Expected Scores** — Honest about difficulty levels

---

## Summary

Your README explains **what you built**, **why it matters**, **how to use it**, and **what success looks like**.

For judges: It answers all questions before they ask them.  
For users: It enables them to clone and run without external help.  
For HF: It becomes your Space's presentation layer.

**Total value:** Differentiator in a competitive hackathon. 📊
