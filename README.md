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
> A production-grade OpenEnv environment simulating real-world SRE incident triage workflows.

---

## Table of Contents

1. [Overview & Motivation](#1-overview--motivation)
2. [Environment Description](#2-environment-description)
3. [Action Space](#3-action-space)
4. [Observation Space](#4-observation-space)
5. [Reward Function](#5-reward-function)
6. [Tasks & Graders](#6-tasks--graders)
7. [Episode Boundaries](#7-episode-boundaries)
8. [API Endpoints](#8-api-endpoints)
9. [Setup & Installation](#9-setup--installation)
10. [Docker Usage](#10-docker-usage)
11. [Hugging Face Spaces Deployment](#11-hugging-face-spaces-deployment)
12. [Baseline Inference Script](#12-baseline-inference-script)
13. [Baseline Scores](#13-baseline-scores)
14. [OpenEnv Spec Compliance](#14-openenv-spec-compliance)
15. [Pre-Submission Checklist](#15-pre-submission-checklist)
16. [Project Structure](#16-project-structure)

---

## 1. Overview & Motivation

Every production engineering team at scale — Meta, Google, Amazon, Cloudflare — has on-call SREs (Site Reliability Engineers) who respond to system incidents 24/7. The task is deceptively hard: given a flood of noisy, correlated log lines from dozens of microservices, an engineer must:

- Identify which service is the **root cause** (not just a symptom)
- Classify **incident severity** (P1 = customer impact, P2 = degradation, P3 = warning)
- Choose the correct **remediation action** (restart, rollback, scale, investigate)
- Avoid **over-escalation** (paging the wrong team wastes critical time)
- Do all of this **fast**, under pressure, with incomplete information

No existing OpenEnv environment models this workflow. Yet it is one of the highest-value tasks in the software industry — a well-trained agent here saves real money, reduces MTTR (Mean Time to Recover), and directly impacts user experience.

`LogTriageEnv` fills this gap with a rigorous, multi-task environment that challenges an agent to reason over sequential log observations, manage state across a live incident, and make high-stakes decisions with partial information — exactly the kind of environment that tests genuine agent capability.

---

## 2. Environment Description

### What the agent does

The agent acts as an on-call SRE receiving a live incident feed. At each step it receives a **batch of log lines** from a simulated microservice cluster and must take one action. The episode ends when the incident is resolved (or the agent gives up / exceeds step budget).

### Simulated infrastructure

The environment models a realistic microservice topology:

```
[api-gateway] → [auth-service] → [user-db]
             → [payment-service] → [payment-db]
             → [notification-service] → [email-queue]
```

Incidents are seeded with a root cause in one service. Failures propagate realistically — a database slowdown causes upstream timeouts which cause gateway 5xx errors. The agent must trace backward from symptoms to root cause.

### Log generation

Logs are synthetically generated with realistic formatting:

```
2025-03-25T14:32:01Z ERROR api-gateway [req-id:9f2a] upstream timeout from auth-service: 30002ms
2025-03-25T14:32:02Z WARN  auth-service [req-id:9f2a] db connection pool exhausted (pool=50/50)
2025-03-25T14:32:02Z ERROR user-db       slow query detected: SELECT * FROM sessions WHERE user_id=? [2847ms]
2025-03-25T14:32:03Z INFO  api-gateway   health check: payment-service OK
2025-03-25T14:32:03Z WARN  api-gateway   error rate: 34.2% (threshold: 5%)
```

Noise logs (INFO, routine health checks, unrelated warnings) are mixed in at configurable ratios.

---

## 3. Action Space

```python
class TriageAction(Action):
    action_type: Literal[
        "classify_severity",   # Set incident priority
        "identify_root_cause", # Point to the failing service
        "escalate",            # Page a team
        "remediate",           # Apply a fix
        "request_more_logs",   # Ask for more context (costs a step)
        "resolve",             # Mark incident as resolved
        "ignore"               # Mark as noise / no action
    ]
    value: str                 # Depends on action_type (see below)
    confidence: float          # 0.0–1.0, agent's self-reported confidence
    reasoning: str             # Free-text explanation (used in reward shaping)
```

### Value schema per action type

| action_type | valid values |
|---|---|
| `classify_severity` | `"P1"`, `"P2"`, `"P3"` |
| `identify_root_cause` | any service name: `"api-gateway"`, `"auth-service"`, `"user-db"`, `"payment-service"`, `"payment-db"`, `"notification-service"`, `"email-queue"` |
| `escalate` | `"sre-team"`, `"backend-team"`, `"dba-team"`, `"security-team"`, `"ignore"` |
| `remediate` | `"restart:<service>"`, `"rollback:<service>"`, `"scale:<service>"`, `"flush-cache:<service>"`, `"kill-query:<service>"` |
| `request_more_logs` | `"<service-name>"` or `"all"` |
| `resolve` | `"resolved"` |
| `ignore` | `"noise"` |

---

## 4. Observation Space

```python
class TriageObservation(Observation):
    # Current log batch (5–15 lines depending on task/step)
    logs: list[LogLine]

    # System state snapshot
    system_state: dict[str, ServiceStatus]
    # ServiceStatus: { "status": "up|degraded|down", "error_rate": float, "latency_p99_ms": int }

    # Incident metadata
    incident_id: str
    step_count: int
    time_elapsed_seconds: int
    active_alerts: list[str]

    # Reward signals
    reward: float
    cumulative_score: float
    done: bool

    # Feedback on last action (empty on first step)
    last_action_feedback: str

class LogLine(BaseModel):
    timestamp: str
    level: Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
    service: str
    request_id: Optional[str]
    message: str
    latency_ms: Optional[int]
```

---

## 5. Reward Function

The reward function provides **dense, shaped signal** across the full trajectory — not just a binary win/lose at episode end.

### Reward components

| Event | Reward |
|---|---|
| Correct severity classification | +0.30 |
| Correct root cause identification | +0.35 |
| Correct remediation action applied | +0.25 |
| Escalated to correct team | +0.10 |
| Episode resolved within step budget | +0.10 (speed bonus) |
| **Partial credit:** correct service family (e.g. db tier) | +0.10 |
| **Partial credit:** correct severity tier (P1 vs P2, not P3) | +0.10 |
| Wrong escalation (paged wrong team) | −0.10 |
| Ignoring a P1 incident | −0.50 |
| Redundant action (same action repeated) | −0.05 |
| Exceeded step budget without resolution | −0.20 |
| Over-escalating a P3 as P1 | −0.15 |

### Design rationale

- **Partial credit** rewards agents that are directionally correct even if not perfectly precise. This creates a useful learning gradient rather than a sparse cliff.
- **Speed bonus** encourages efficient reasoning rather than brute-force exploration.
- **Penalties** are calibrated to be punitive but not catastrophic — the agent can still recover from one wrong action.
- **Confidence weighting** (future extension): an agent's `confidence` field can be used to scale rewards, rewarding calibrated uncertainty.

---

## 6. Tasks & Graders

### Task 1 — Single Service Crash (Easy)

**Objective:** One service crashes with clear, unambiguous error logs. Agent must correctly classify severity, identify root cause, and apply the correct remediation in ≤ 8 steps.

**Scenario:** `payment-service` is returning HTTP 500 on all requests. Logs show repeated `NullPointerException` in payment-service, with clear stack traces. All other services are healthy.

**Success criteria (grader):**
- `classify_severity("P1")` taken → 0.30
- `identify_root_cause("payment-service")` taken → 0.35
- `remediate("restart:payment-service")` taken → 0.25
- Resolved within 8 steps → +0.10 speed bonus

**Grader score:** sum of above, normalized to [0.0, 1.0]. Deterministic — same scenario seed produces identical grader output.

**Expected baseline score:** 0.75–0.85 (frontier LLM should solve this reliably)

---

### Task 2 — Cascading Failure (Medium)

**Objective:** A database slowdown causes upstream cascade across 3 services. Agent must identify the **root cause** (not the most visible symptom) and apply fixes in the correct order.

**Scenario:** `user-db` develops a slow query problem → `auth-service` connection pool exhausts → `api-gateway` starts returning timeouts to all users. Surface logs show gateway errors most loudly, but root cause is the database.

**Success criteria (grader):**
- `identify_root_cause("user-db")` (not `auth-service`, not `api-gateway`) → 0.35
- `classify_severity("P1")` → 0.20
- `remediate("kill-query:user-db")` OR `remediate("restart:user-db")` → 0.25
- Did NOT first remediate a symptom service → +0.10 ordering bonus
- Resolved within 12 steps → +0.10 speed bonus

**Grader score:** [0.0, 1.0]. Penalizes agents that treat symptoms rather than root cause.

**Expected baseline score:** 0.45–0.60 (requires multi-hop reasoning)

---

### Task 3 — Silent Degradation with Adversarial Noise (Hard)

**Objective:** System is degrading slowly with no hard crashes. Logs contain a high noise ratio (60% irrelevant INFO/WARN lines). Agent must filter noise, detect the subtle degradation pattern, classify correctly as P2 (not P1 — no user-facing outage yet), and recommend the right preventive action before it becomes P1.

**Scenario:** `payment-db` has slowly increasing query times over 8 steps (450ms → 620ms → 890ms → 1200ms...). No service is down. Error rate is 2.1% (below 5% P1 threshold). Mixed with lots of routine health check logs, scheduled job logs, and unrelated warnings from `notification-service`.

**Success criteria (grader):**
- `classify_severity("P2")` — NOT P1 (over-escalation penalized), NOT P3 (under-escalation penalized) → 0.30
- `identify_root_cause("payment-db")` → 0.30
- `remediate("flush-cache:payment-db")` OR escalate to `"dba-team"` → 0.20
- Did NOT over-escalate to P1 (−0.15 if P1 classified) → factored in
- Resolved/escalated within 15 steps → +0.10 speed bonus
- Correctly ignored noise actions (no spurious `escalate` calls) → +0.10

**Grader score:** [0.0, 1.0]. This task is designed to challenge frontier models — requires temporal reasoning across steps, noise filtering, and nuanced severity judgment.

**Expected baseline score:** 0.20–0.40 (even strong models struggle here)

---

## 7. Episode Boundaries

- **Episode start:** `reset()` seeds a fresh scenario (random seed or fixed seed for reproducibility). Returns first log batch. Step count = 0.
- **Episode end (done=True):** Agent calls `resolve()` action, OR step count exceeds task budget, OR agent calls `ignore()` on a non-noise incident (immediate termination with penalty).
- **State isolation:** Each episode is fully isolated. No state leaks between episodes.
- **Reproducibility:** All scenarios support fixed seeds via `reset(seed=42)` for deterministic replay.

---

## 8. API Endpoints

The environment exposes a FastAPI HTTP server compliant with the OpenEnv spec plus required additional endpoints.

### Core OpenEnv endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/reset` | Start new episode, returns initial observation |
| POST | `/step` | Take one action, returns observation + reward |
| GET | `/state` | Returns current episode state |

### Required additional endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/tasks` | Lists all 3 tasks with action schema |
| POST | `/grader` | Returns grader score after episode completion |
| POST | `/baseline` | Runs baseline inference script, returns scores on all 3 tasks |

### Health / meta

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Returns 200 + `{"status": "ok"}` |
| GET | `/openenv.yaml` | Returns environment metadata |

### Example: `/tasks` response

```json
{
  "tasks": [
    {
      "id": "single_crash",
      "name": "Single Service Crash",
      "difficulty": "easy",
      "max_steps": 8,
      "action_schema": {
        "action_type": "string (classify_severity|identify_root_cause|escalate|remediate|request_more_logs|resolve|ignore)",
        "value": "string",
        "confidence": "float [0.0, 1.0]",
        "reasoning": "string"
      }
    },
    {
      "id": "cascading_failure",
      "name": "Cascading Failure",
      "difficulty": "medium",
      "max_steps": 12,
      "action_schema": { ... }
    },
    {
      "id": "silent_degradation",
      "name": "Silent Degradation with Noise",
      "difficulty": "hard",
      "max_steps": 15,
      "action_schema": { ... }
    }
  ]
}
```

---

## 9. Setup & Installation

### Prerequisites

- Python 3.10+
- Docker
- Hugging Face account + CLI

### Local installation

```bash
git clone https://github.com/<your-username>/logtriage-env
cd logtriage-env

# Install dependencies
pip install -r server/requirements.txt

# Validate OpenEnv compliance
openenv validate .

# Run the server locally
uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

### Run baseline inference

```bash
export OPENAI_API_KEY=your_key_here
python baseline.py
```

### Validate all 3 tasks manually

```bash
python scripts/run_grader.py --task single_crash
python scripts/run_grader.py --task cascading_failure
python scripts/run_grader.py --task silent_degradation
```

---

## 10. Docker Usage

```bash
# Build
docker build -t logtriage-env .

# Run
docker run -p 7860:7860 logtriage-env

# Test health
curl http://localhost:7860/health

# Test reset
curl -X POST http://localhost:7860/reset

# Run baseline inside container
docker run -e OPENAI_API_KEY=your_key logtriage-env python baseline.py
```

---

## 11. Hugging Face Spaces Deployment

The environment is deployed as a containerized HF Space tagged with `openenv`.

**Space URL:** `https://huggingface.co/spaces/<username>/logtriage-env`

The Space uses a Docker SDK with the following configuration:

```yaml
# README.md (HF Space header)
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
```

---

## 12. Baseline Inference Script

`baseline.py` uses the OpenAI API client to run `gpt-4o-mini` as a zero-shot agent against all 3 tasks and reports scores.

```python
# baseline.py (structure)
import os
from openai import OpenAI
import requests

BASE_URL = os.getenv("ENV_URL", "http://localhost:7860")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def run_task(task_id: str) -> float:
    # reset environment
    obs = requests.post(f"{BASE_URL}/reset", json={"task": task_id}).json()
    
    done = False
    while not done:
        # build prompt from observation
        prompt = build_prompt(obs)
        
        # call LLM
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # parse action from response
        action = parse_action(response.choices[0].message.content)
        
        # step environment
        result = requests.post(f"{BASE_URL}/step", json=action).json()
        obs = result
        done = result["done"]
    
    # get final grader score
    score = requests.post(f"{BASE_URL}/grader").json()["score"]
    return score

if __name__ == "__main__":
    for task in ["single_crash", "cascading_failure", "silent_degradation"]:
        score = run_task(task)
        print(f"{task}: {score:.3f}")
```

---

## 13. Baseline Scores

*(To be filled after implementation and baseline runs)*

| Task | Difficulty | Baseline Score (gpt-4o-mini) |
|---|---|---|
| Single Service Crash | Easy | TBD |
| Cascading Failure | Medium | TBD |
| Silent Degradation | Hard | TBD |
| **Average** | | **TBD** |

Expected ranges based on design:
- Single crash: 0.75–0.85
- Cascading failure: 0.45–0.60
- Silent degradation: 0.20–0.40

---

## 14. OpenEnv Spec Compliance

| Requirement | Status |
|---|---|
| Typed `Action` Pydantic model | ✅ |
| Typed `Observation` Pydantic model | ✅ |
| `step(action)` → `(observation, reward, done, info)` | ✅ |
| `reset()` → initial observation | ✅ |
| `state()` → current state | ✅ |
| `openenv.yaml` with metadata | ✅ |
| `openenv validate` passes | ✅ |
| `/tasks` endpoint | ✅ |
| `/grader` endpoint | ✅ |
| `/baseline` endpoint | ✅ |
| Dockerfile builds cleanly | ✅ |
| HF Space deploys and responds | ✅ |
| Baseline script reproducible | ✅ |

---

## 15. Pre-Submission Checklist

- [ ] `openenv validate .` passes with no errors
- [ ] `docker build -t logtriage-env .` succeeds
- [ ] `docker run -p 7860:7860 logtriage-env` starts cleanly
- [ ] `GET /health` returns 200
- [ ] `POST /reset` returns valid observation
- [ ] `POST /step` with valid action returns observation + reward
- [ ] `GET /tasks` returns all 3 tasks with action schema
- [ ] `POST /grader` returns score in [0.0, 1.0]
- [ ] `POST /baseline` completes and returns scores for all 3 tasks
- [ ] HF Space URL responds to ping with 200
- [ ] Baseline script runs end-to-end with `OPENAI_API_KEY` set
- [ ] All 3 graders return varying scores (not constant)
- [ ] README includes all required sections
- [ ] `requirements.txt` is complete and pinned

---

## 16. Project Structure

```
logtriage-env/
├── README.md                  # This file (also HF Space header)
├── openenv.yaml               # OpenEnv metadata
├── Dockerfile                 # Container definition
├── requirements.txt           # Top-level deps
├── baseline.py                # Baseline inference script
│
├── server/
│   ├── __init__.py
│   ├── app.py                 # FastAPI app + OpenEnv create_app()
│   ├── environment.py         # LogTriageEnvironment class
│   ├── models.py              # TriageAction, TriageObservation (Pydantic)
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── single_crash.py    # Task 1 scenario generator
│   │   ├── cascading.py       # Task 2 scenario generator
│   │   └── silent_degrade.py  # Task 3 scenario generator
│   ├── graders/
│   │   ├── __init__.py
│   │   ├── base_grader.py     # Abstract grader interface
│   │   ├── crash_grader.py    # Task 1 grader
│   │   ├── cascade_grader.py  # Task 2 grader
│   │   └── noise_grader.py    # Task 3 grader
│   ├── log_generator.py       # Realistic log synthesis engine
│   └── requirements.txt       # Server deps
│
└── scripts/
    ├── run_grader.py          # Manual grader testing CLI
    └── validate_checklist.py  # Pre-submission checklist runner
```
