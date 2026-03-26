# Day 1 — Execution Plan
**LogTriageEnv | Meta × PyTorch Hackathon**
**Date: March 25, 2026 | Deadline: April 7, 11:59 PM IST**

---

## Goal for Today
By end of Day 1 you must have:
- [ ] GitHub repo created and cloned locally
- [ ] Folder structure scaffolded
- [ ] `openenv.yaml` written and valid
- [ ] `models.py` complete (TriageAction + TriageObservation fully typed)
- [ ] `app.py` skeleton running locally (server starts without errors)
- [ ] `Dockerfile` skeleton (builds successfully, even if app is minimal)
- [ ] First `git push` to GitHub

---

## Step 1 — Create GitHub Repo

Go to github.com → New Repository
- Name: `logtriage-env`
- Visibility: **Public** (required for submission)
- Add README: **No** (we have our own)
- .gitignore: **Python**

Then clone it locally:

```bash
cd C:\Users\Rohit\Desktop
git clone https://github.com/rohitdecodes/logtriage-env
cd logtriage-env
```

---

## Step 2 — Create Folder Structure

Run this in your terminal inside the `logtriage-env` folder:

```bash
mkdir server
mkdir server\scenarios
mkdir server\graders
mkdir scripts

type nul > openenv.yaml
type nul > Dockerfile
type nul > requirements.txt
type nul > baseline.py
type nul > README.md
type nul > server\__init__.py
type nul > server\app.py
type nul > server\environment.py
type nul > server\models.py
type nul > server\log_generator.py
type nul > server\requirements.txt
type nul > server\scenarios\__init__.py
type nul > server\scenarios\single_crash.py
type nul > server\scenarios\cascading.py
type nul > server\scenarios\silent_degrade.py
type nul > server\graders\__init__.py
type nul > server\graders\base_grader.py
type nul > server\graders\crash_grader.py
type nul > server\graders\cascade_grader.py
type nul > server\graders\noise_grader.py
type nul > scripts\run_grader.py
type nul > scripts\validate_checklist.py
```

Verify structure looks correct:
```bash
tree /F
```

---

## Step 3 — Install Dependencies

```bash
pip install openenv-core fastapi uvicorn pydantic
```

Then create `requirements.txt`:

```
openenv-core>=0.2.2
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.0.0
requests>=2.25.0
openai>=1.0.0
```

---

## Step 4 — Write `openenv.yaml`

Open `openenv.yaml` and paste this exactly:

```yaml
name: logtriage-env
version: 1.0.0
description: >
  An OpenEnv environment where an AI agent acts as an on-call SRE.
  The agent receives live system logs from a simulated microservice cluster
  and must diagnose, prioritize, and resolve incidents across 3 tasks
  of increasing difficulty.
author: Rohit Patil
tags:
  - openenv
  - sre
  - log-analysis
  - incident-response
  - reinforcement-learning
tasks:
  - id: single_crash
    name: Single Service Crash
    difficulty: easy
    max_steps: 8
    description: One service crashes with clear error logs. Classify, identify root cause, remediate.
  - id: cascading_failure
    name: Cascading Failure
    difficulty: medium
    max_steps: 12
    description: Database slowdown causes upstream cascade. Find root cause, not just symptoms.
  - id: silent_degradation
    name: Silent Degradation with Noise
    difficulty: hard
    max_steps: 15
    description: Slow degradation hidden in 60% noise. Nuanced severity judgment required.
action_space:
  type: discrete
  description: SRE triage actions — classify, identify, escalate, remediate, resolve
observation_space:
  type: structured
  description: Log batches + system state + incident metadata per step
reward_range: [-0.5, 1.0]
```

---

## Step 5 — Write `server/models.py`

This is the most important file today. Open `server/models.py` and paste:

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ─── LOG LINE ─────────────────────────────────────────────────────────────────

class LogLine(BaseModel):
    """A single log line from the simulated microservice cluster."""
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    level: Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
    service: str = Field(..., description="Service that emitted the log")
    request_id: Optional[str] = Field(None, description="Request trace ID if present")
    message: str = Field(..., description="Log message content")
    latency_ms: Optional[int] = Field(None, description="Latency if relevant")


# ─── SERVICE STATUS ────────────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    """Current health snapshot of one microservice."""
    name: str
    status: Literal["up", "degraded", "down"]
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Error rate 0.0-1.0")
    latency_p99_ms: int = Field(..., description="99th percentile latency in ms")
    last_updated: str = Field(..., description="ISO 8601 timestamp of last update")


# ─── ACTION ───────────────────────────────────────────────────────────────────

class TriageAction(BaseModel):
    """
    Action taken by the agent in one step.

    action_type options:
      - classify_severity  : value must be "P1", "P2", or "P3"
      - identify_root_cause: value must be a valid service name
      - escalate           : value must be a valid team name
      - remediate          : value must be "restart:<svc>", "rollback:<svc>",
                             "scale:<svc>", "flush-cache:<svc>", "kill-query:<svc>"
      - request_more_logs  : value must be a service name or "all"
      - resolve            : value must be "resolved"
      - ignore             : value must be "noise"
    """
    action_type: Literal[
        "classify_severity",
        "identify_root_cause",
        "escalate",
        "remediate",
        "request_more_logs",
        "resolve",
        "ignore",
    ] = Field(..., description="Type of triage action to perform")

    value: str = Field(
        ...,
        description="Action value — depends on action_type (see docstring)"
    )

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agent self-reported confidence in this action (0.0-1.0)"
    )

    reasoning: str = Field(
        default="",
        description="Optional free-text reasoning (used for interpretability)"
    )

    # ── Valid value constants ──────────────────────────────────────────────────
    VALID_SEVERITIES = {"P1", "P2", "P3"}
    VALID_SERVICES = {
        "api-gateway",
        "auth-service",
        "user-db",
        "payment-service",
        "payment-db",
        "notification-service",
        "email-queue",
    }
    VALID_TEAMS = {
        "sre-team",
        "backend-team",
        "dba-team",
        "security-team",
    }
    VALID_REMEDIATION_PREFIXES = {
        "restart",
        "rollback",
        "scale",
        "flush-cache",
        "kill-query",
    }

    def is_valid(self) -> tuple[bool, str]:
        """
        Validate the action value against its action_type.
        Returns (is_valid: bool, error_message: str).
        """
        if self.action_type == "classify_severity":
            if self.value not in self.VALID_SEVERITIES:
                return False, f"classify_severity value must be one of {self.VALID_SEVERITIES}"

        elif self.action_type == "identify_root_cause":
            if self.value not in self.VALID_SERVICES:
                return False, f"identify_root_cause value must be one of {self.VALID_SERVICES}"

        elif self.action_type == "escalate":
            if self.value not in self.VALID_TEAMS:
                return False, f"escalate value must be one of {self.VALID_TEAMS}"

        elif self.action_type == "remediate":
            prefix = self.value.split(":")[0]
            if prefix not in self.VALID_REMEDIATION_PREFIXES:
                return False, f"remediate prefix must be one of {self.VALID_REMEDIATION_PREFIXES}"
            parts = self.value.split(":")
            if len(parts) != 2 or parts[1] not in self.VALID_SERVICES:
                return False, f"remediate format must be '<action>:<service>'"

        elif self.action_type == "request_more_logs":
            if self.value != "all" and self.value not in self.VALID_SERVICES:
                return False, f"request_more_logs value must be 'all' or a valid service name"

        elif self.action_type == "resolve":
            if self.value != "resolved":
                return False, "resolve value must be 'resolved'"

        elif self.action_type == "ignore":
            if self.value != "noise":
                return False, "ignore value must be 'noise'"

        return True, ""


# ─── OBSERVATION ──────────────────────────────────────────────────────────────

class TriageObservation(BaseModel):
    """
    Observation returned to the agent after each step (and after reset).
    Contains the current log batch, system state, incident metadata,
    and reward signals.
    """
    # Log batch for this step
    logs: list[LogLine] = Field(
        ...,
        description="Current batch of log lines (5-15 lines)"
    )

    # System state snapshot
    system_state: dict[str, ServiceStatus] = Field(
        ...,
        description="Per-service health snapshot keyed by service name"
    )

    # Incident metadata
    incident_id: str = Field(..., description="Unique ID for this episode")
    task_id: str = Field(..., description="Which task is being run")
    step_count: int = Field(..., description="Current step number (0-indexed)")
    time_elapsed_seconds: int = Field(
        ...,
        description="Simulated incident time elapsed in seconds"
    )
    active_alerts: list[str] = Field(
        default_factory=list,
        description="Currently firing alert names"
    )

    # Reward signals
    reward: float = Field(
        default=0.0,
        description="Reward received for the last action"
    )
    cumulative_score: float = Field(
        default=0.0,
        description="Running total score for this episode"
    )
    done: bool = Field(
        default=False,
        description="Whether the episode has ended"
    )

    # Feedback
    last_action_feedback: str = Field(
        default="",
        description="Natural language feedback on the previous action"
    )
    invalid_action_error: Optional[str] = Field(
        default=None,
        description="Set if the last action was invalid (wrong format/value)"
    )


# ─── EPISODE STATE ────────────────────────────────────────────────────────────

class EpisodeState(BaseModel):
    """Internal state of the current episode (returned by state() endpoint)."""
    episode_id: str
    task_id: str
    step_count: int
    max_steps: int
    done: bool
    cumulative_score: float
    actions_taken: list[str] = Field(
        default_factory=list,
        description="List of action_type values taken so far this episode"
    )
    correct_severity: Optional[str] = Field(
        None,
        description="Whether agent has correctly classified severity yet"
    )
    correct_root_cause: Optional[str] = Field(
        None,
        description="Whether agent has correctly identified root cause yet"
    )
    correct_remediation: bool = False
```

---

## Step 6 — Write `server/app.py` Skeleton

Open `server/app.py` and paste:

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from server.models import TriageAction, TriageObservation, EpisodeState

app = FastAPI(
    title="LogTriageEnv",
    description="OpenEnv environment for SRE incident triage",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "environment": "logtriage-env", "version": "1.0.0"}


@app.post("/reset")
def reset(task: str = "single_crash", seed: int = None):
    # TODO Day 2: wire to LogTriageEnvironment
    return {"message": "reset endpoint placeholder", "task": task}


@app.post("/step")
def step(action: TriageAction):
    # TODO Day 2: wire to LogTriageEnvironment
    valid, err = action.is_valid()
    if not valid:
        return JSONResponse(status_code=422, content={"error": err})
    return {"message": "step endpoint placeholder", "action_received": action.model_dump()}


@app.get("/state")
def state():
    # TODO Day 2: wire to LogTriageEnvironment
    return {"message": "state endpoint placeholder"}


@app.get("/tasks")
def get_tasks():
    return {
        "tasks": [
            {
                "id": "single_crash",
                "name": "Single Service Crash",
                "difficulty": "easy",
                "max_steps": 8,
                "description": "One service crashes. Classify severity, find root cause, remediate.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "cascading_failure",
                "name": "Cascading Failure",
                "difficulty": "medium",
                "max_steps": 12,
                "description": "DB slowdown cascades upstream. Find the true root cause.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "silent_degradation",
                "name": "Silent Degradation with Noise",
                "difficulty": "hard",
                "max_steps": 15,
                "description": "Slow degradation hidden in 60% noise. Nuanced P2 judgment.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
        ]
    }


@app.post("/grader")
def grader():
    # TODO Day 4: wire to grader logic
    return {"message": "grader endpoint placeholder", "score": 0.0}


@app.post("/baseline")
def baseline():
    # TODO Day 5: wire to baseline.py
    return {"message": "baseline endpoint placeholder"}


if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=True)
```

---

## Step 7 — Write `Dockerfile` Skeleton

Open `Dockerfile` and paste:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source
COPY . .

# Expose port (HF Spaces uses 7860)
EXPOSE 7860

# Start server
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
```

---

## Step 8 — Test Everything Locally

### 8a. Start the server

```bash
cd C:\Users\Rohit\Desktop\logtriage-env
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:7860
INFO:     Application startup complete.
```

### 8b. Test endpoints (open a second terminal)

```bash
# Health check
curl http://localhost:7860/health

# Tasks list
curl http://localhost:7860/tasks

# Test reset placeholder
curl -X POST "http://localhost:7860/reset?task=single_crash"

# Test step with valid action
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"classify_severity\", \"value\": \"P1\", \"confidence\": 0.9, \"reasoning\": \"High error rate\"}"

# Test step with INVALID action (should return 422)
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"classify_severity\", \"value\": \"P5\", \"confidence\": 0.9, \"reasoning\": \"test\"}"
```

All of these should return JSON responses without crashing the server.

### 8c. Test Docker build

```bash
docker build -t logtriage-env .
docker run -p 7860:7860 logtriage-env
```

Open browser: `http://localhost:7860/health` → should return `{"status":"ok",...}`

---

## Step 9 — Git Push

```bash
cd C:\Users\Rohit\Desktop\logtriage-env
git add .
git commit -m "Day 1: scaffold, models.py, app skeleton, Dockerfile"
git push origin main
```

---

## Day 1 Done Checklist

Go through each one — do NOT move to Day 2 until all are ticked:

- [ ] `logtriage-env` repo exists on GitHub (public)
- [ ] All folders and files created (`tree /F` shows correct structure)
- [ ] `openenv.yaml` written with all 3 tasks defined
- [ ] `server/models.py` complete — `TriageAction`, `TriageObservation`, `EpisodeState` all defined
- [ ] `server/app.py` skeleton — all 7 endpoints exist and return placeholder JSON
- [ ] `uvicorn server.app:app` starts without errors
- [ ] `curl http://localhost:7860/health` returns 200
- [ ] `curl http://localhost:7860/tasks` returns all 3 tasks
- [ ] `docker build -t logtriage-env .` succeeds
- [ ] `docker run -p 7860:7860 logtriage-env` starts cleanly
- [ ] `git push` done — code visible on GitHub

---

## What NOT to do today

- Do NOT start writing scenario logic (that's Day 2)
- Do NOT start writing graders (that's Day 4)
- Do NOT touch HF Spaces deployment (that's Day 6)
- Do NOT overthink `models.py` — the schema above is final, use it as-is

---

## Tomorrow (Day 2 Preview)

You will write `server/environment.py` (the core `LogTriageEnvironment` class with real `reset()` and `step()` logic), `server/log_generator.py` (synthetic log generation), and Task 1 scenario (`single_crash.py`). The server will go from placeholder responses to a fully functional environment for Task 1.
