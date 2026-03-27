# Day 2 — Execution Plan
**LogTriageEnv | Meta × PyTorch Hackathon**
**Date: March 27, 2026 | Deadline: April 7, 11:59 PM IST**

---

## Goal for Today
By end of Day 2 you must have:
- [ ] `server/log_generator.py` — synthetic log generation engine working
- [ ] `server/scenarios/single_crash.py` — Task 1 scenario fully defined
- [ ] `server/environment.py` — `LogTriageEnvironment` class with real `reset()` and `step()` logic
- [ ] `/reset` and `/step` endpoints returning **real observations** (not placeholders)
- [ ] `/state` endpoint returning real episode state
- [ ] Full Task 1 episode playable end-to-end via curl
- [ ] Git push with all Day 2 work

---

## What Day 2 Builds

Day 1 gave you the skeleton. Day 2 gives it a brain.

```
server/
├── log_generator.py       ← BUILD THIS FIRST (foundation)
├── scenarios/
│   └── single_crash.py   ← BUILD THIS SECOND (Task 1 data)
└── environment.py         ← BUILD THIS LAST (wires everything together)
```

Build in this exact order. `log_generator` feeds `single_crash`, which feeds `environment`.

---

## Step 1 — Write `server/log_generator.py`

This is the engine that generates realistic log lines for any scenario.
Open `server/log_generator.py` and paste:

```python
"""
Log generator for LogTriageEnv.
Produces realistic-looking log lines for the simulated microservice cluster.
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta
from server.models import LogLine, ServiceStatus

# ─── SERVICES ─────────────────────────────────────────────────────────────────

SERVICES = [
    "api-gateway",
    "auth-service",
    "user-db",
    "payment-service",
    "payment-db",
    "notification-service",
    "email-queue",
]

# ─── LOG TEMPLATES ────────────────────────────────────────────────────────────

# Noise logs — realistic but irrelevant to the incident
NOISE_TEMPLATES = {
    "api-gateway": [
        ("INFO",  "health check passed — all upstream services reachable"),
        ("INFO",  "request completed: GET /api/v1/users/profile [200] 45ms"),
        ("INFO",  "rate limiter: 1240/5000 requests this minute"),
        ("DEBUG", "connection pool: 12/100 active connections"),
        ("INFO",  "TLS certificate valid for 87 more days"),
    ],
    "auth-service": [
        ("INFO",  "JWT token issued for user_id=88142 [expires: 3600s]"),
        ("INFO",  "OAuth2 flow completed successfully"),
        ("DEBUG", "session cache hit ratio: 94.2%"),
        ("INFO",  "password reset email queued for user_id=23019"),
    ],
    "user-db": [
        ("INFO",  "daily vacuum completed: 0 dead tuples removed"),
        ("INFO",  "checkpoint complete: wrote 142 buffers"),
        ("DEBUG", "autovacuum: processing table 'sessions'"),
        ("INFO",  "replication lag: 12ms (within threshold)"),
    ],
    "payment-service": [
        ("INFO",  "payment processed: txn_id=TXN-8812 amount=299.00 INR [success]"),
        ("INFO",  "webhook delivered: stripe event=payment.succeeded"),
        ("DEBUG", "idempotency key cache: 2341 keys active"),
    ],
    "payment-db": [
        ("INFO",  "connection pool: 8/50 active"),
        ("DEBUG", "query plan cache: 88% hit ratio"),
        ("INFO",  "index usage: 99.1% queries using indexed scans"),
    ],
    "notification-service": [
        ("INFO",  "email dispatched: template=welcome_email to=user@example.com"),
        ("INFO",  "SMS delivered: +91XXXXXXXXXX [provider=twilio]"),
        ("WARN",  "email bounce rate: 1.2% (threshold: 5%)"),
        ("INFO",  "push notification sent: device_tokens=1240"),
    ],
    "email-queue": [
        ("INFO",  "queue depth: 42 messages pending"),
        ("INFO",  "consumer lag: 0.3s (healthy)"),
        ("DEBUG", "partition rebalance completed in 120ms"),
    ],
}

# Signal logs — actual incident indicators
SIGNAL_TEMPLATES = {
    # Single service crash signals (Task 1 — payment-service crash)
    "single_crash_payment": [
        ("ERROR", "NullPointerException: Cannot invoke method processPayment() on null object — PaymentProcessor.java:142"),
        ("ERROR", "HTTP 500 Internal Server Error: payment gateway returned null response"),
        ("ERROR", "NullPointerException in PaymentService.execute() — retrying (attempt 1/3)"),
        ("ERROR", "NullPointerException in PaymentService.execute() — retrying (attempt 2/3)"),
        ("FATAL", "NullPointerException in PaymentService.execute() — all retries exhausted, request failed"),
        ("ERROR", "health check FAILED: payment-service returned 500 (was 200)"),
        ("ERROR", "circuit breaker OPEN: payment-service error rate 98.2% (threshold: 10%)"),
    ],
    # Cascading failure signals (Task 2 — user-db → auth-service → api-gateway)
    "cascading_userdb": [
        ("WARN",  "slow query detected: SELECT * FROM sessions WHERE user_id=? [latency: 2847ms, threshold: 200ms]"),
        ("ERROR", "slow query detected: SELECT * FROM sessions WHERE user_id=? [latency: 4120ms]"),
        ("ERROR", "query timeout: SELECT * FROM active_sessions [timeout after 5000ms]"),
    ],
    "cascading_auth": [
        ("WARN",  "db connection pool: 42/50 active connections (84% utilization)"),
        ("ERROR", "db connection pool exhausted: 50/50 connections in use — requests queuing"),
        ("ERROR", "authentication request timed out waiting for db connection [5200ms]"),
    ],
    "cascading_gateway": [
        ("ERROR", "upstream timeout: auth-service failed to respond within 5000ms [req-id: {req_id}]"),
        ("ERROR", "upstream timeout: auth-service [req-id: {req_id}] — returning 504 to client"),
        ("WARN",  "error rate spike: 34.2% of requests failing (threshold: 5%)"),
    ],
    # Silent degradation signals (Task 3 — payment-db slow)
    "silent_paymentdb": [
        ("WARN",  "query latency elevated: avg=450ms (normal: 80ms) — monitoring"),
        ("WARN",  "query latency elevated: avg=620ms — possible memory pressure"),
        ("WARN",  "query latency elevated: avg=890ms — recommend investigation"),
        ("WARN",  "query latency elevated: avg=1200ms — approaching timeout threshold"),
        ("WARN",  "buffer cache hit ratio degraded: 87% (normal: 98%) — possible memory issue"),
    ],
}


def _make_timestamp(base_time: datetime, offset_seconds: int = 0) -> str:
    t = base_time + timedelta(seconds=offset_seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _noise_log(service: str, base_time: datetime, offset: int) -> LogLine:
    templates = NOISE_TEMPLATES.get(service, [("INFO", "routine operation completed")])
    level, message = random.choice(templates)
    return LogLine(
        timestamp=_make_timestamp(base_time, offset),
        level=level,
        service=service,
        request_id=None,
        message=message,
        latency_ms=None,
    )


def generate_log_batch(
    scenario_signals: list[tuple[str, str, str]],  # [(service, level, message), ...]
    step: int,
    base_time: datetime,
    noise_ratio: float = 0.3,
    batch_size: int = 8,
    rng: random.Random = None,
) -> list[LogLine]:
    """
    Generate a mixed batch of signal + noise log lines.

    Args:
        scenario_signals: List of (service, level, message) tuples — the actual signals for this step
        step: Current step number (used for timestamp offset)
        base_time: Episode start time (used for timestamps)
        noise_ratio: Fraction of logs that are noise (0.0 = all signal, 1.0 = all noise)
        batch_size: Total number of log lines to return
        rng: Optional seeded Random for reproducibility

    Returns:
        List of LogLine objects, shuffled (signal mixed into noise)
    """
    if rng is None:
        rng = random.Random()

    logs = []
    base_offset = step * 30  # 30 simulated seconds per step

    # Add signal logs
    for i, (service, level, message) in enumerate(scenario_signals):
        req_id = f"req-{rng.randint(1000, 9999)}" if level in ("ERROR", "WARN") else None
        logs.append(LogLine(
            timestamp=_make_timestamp(base_time, base_offset + i),
            level=level,
            service=service,
            request_id=req_id,
            message=message,
            latency_ms=rng.randint(200, 5000) if "timeout" in message.lower() or "latency" in message.lower() else None,
        ))

    # Fill remaining slots with noise logs
    noise_count = max(0, batch_size - len(logs))
    noise_services = rng.choices(SERVICES, k=noise_count)
    for i, svc in enumerate(noise_services):
        logs.append(_noise_log(svc, base_time, base_offset + len(scenario_signals) + i))

    # Shuffle — signal should not always be first
    rng.shuffle(logs)
    return logs[:batch_size]


def generate_healthy_system_state(base_time: datetime) -> dict[str, ServiceStatus]:
    """Generate a fully healthy system state snapshot."""
    now = _make_timestamp(base_time)
    return {
        svc: ServiceStatus(
            name=svc,
            status="up",
            error_rate=round(random.uniform(0.001, 0.01), 4),
            latency_p99_ms=random.randint(20, 80),
            last_updated=now,
        )
        for svc in SERVICES
    }
```

---

## Step 2 — Write `server/scenarios/single_crash.py`

This defines Task 1: the payment-service crash scenario.
Open `server/scenarios/single_crash.py` and paste:

```python
"""
Task 1 — Single Service Crash (Easy)

Scenario: payment-service crashes with NullPointerException on every request.
All other services are healthy. Logs are mostly unambiguous.
Noise ratio: ~20%.

Ground truth:
  - severity: P1
  - root_cause: payment-service
  - remediation: restart:payment-service
  - correct_team: backend-team
"""
from __future__ import annotations
import random
from datetime import datetime
from server.models import LogLine, ServiceStatus
from server.log_generator import (
    generate_log_batch,
    generate_healthy_system_state,
    SIGNAL_TEMPLATES,
    _make_timestamp,
)

# ─── GROUND TRUTH ─────────────────────────────────────────────────────────────

GROUND_TRUTH = {
    "severity": "P1",
    "root_cause": "payment-service",
    "remediation_prefixes": {"restart"},          # restart:payment-service is correct
    "remediation_service": "payment-service",
    "correct_teams": {"backend-team", "sre-team"},
    "max_steps": 8,
    "noise_ratio": 0.20,
}

# ─── STEP-BY-STEP SIGNAL PLAN ─────────────────────────────────────────────────
# Each list = signals injected at that step index.
# Step 0 = after reset (first observation), Step 7 = last possible step.

STEP_SIGNALS = [
    # Step 0: first signs — circuit breaker opens, error rate spike
    [
        ("payment-service", "ERROR", "NullPointerException: Cannot invoke processPayment() on null — PaymentProcessor.java:142"),
        ("api-gateway",     "WARN",  "error rate spike: 28.4% of /payment requests failing"),
    ],
    # Step 1: escalating — more errors, health check fails
    [
        ("payment-service", "FATAL", "NullPointerException in PaymentService.execute() — all retries (3/3) exhausted"),
        ("payment-service", "ERROR", "health check FAILED: payment-service returned HTTP 500"),
    ],
    # Step 2: circuit breaker fully open
    [
        ("api-gateway",     "ERROR", "circuit breaker OPEN: payment-service error rate 98.2% (threshold: 10%)"),
        ("payment-service", "ERROR", "NullPointerException: Cannot invoke processPayment() on null — PaymentProcessor.java:142"),
    ],
    # Step 3+: same signals repeat — incident ongoing until agent acts
    [
        ("payment-service", "ERROR", "NullPointerException in PaymentService.execute() — retrying (1/3)"),
        ("api-gateway",     "ERROR", "upstream failure: payment-service unavailable [circuit breaker: OPEN]"),
    ],
    [
        ("payment-service", "FATAL", "payment-service health check FAILED for 90s — marking as DOWN"),
        ("api-gateway",     "WARN",  "payment endpoint degraded — all requests returning 503"),
    ],
    [
        ("payment-service", "ERROR", "NullPointerException: Cannot invoke processPayment() on null — PaymentProcessor.java:142"),
        ("api-gateway",     "ERROR", "error rate: 99.1% on /payment/* routes"),
    ],
    [
        ("payment-service", "FATAL", "NullPointerException — service unresponsive for 180s"),
        ("api-gateway",     "ERROR", "SLA breach: payment service uptime < 99.9%"),
    ],
    [
        ("payment-service", "FATAL", "CRITICAL: payment-service has been DOWN for 210s — immediate action required"),
        ("api-gateway",     "ERROR", "all payment transactions failing — revenue impact ongoing"),
    ],
]


def get_system_state(step: int, base_time: datetime) -> dict[str, ServiceStatus]:
    """Return system state for this step. payment-service is down; others are healthy."""
    now = _make_timestamp(base_time, step * 30)
    state = generate_healthy_system_state(base_time)

    # Override payment-service to be DOWN
    state["payment-service"] = ServiceStatus(
        name="payment-service",
        status="down",
        error_rate=0.982,
        latency_p99_ms=5000,
        last_updated=now,
    )
    return state


def get_step_data(step: int, base_time: datetime, rng: random.Random) -> tuple[list[LogLine], dict[str, ServiceStatus]]:
    """
    Returns (logs, system_state) for the given step.
    Signals get louder over time if agent hasn't acted.
    """
    signal_idx = min(step, len(STEP_SIGNALS) - 1)
    signals = STEP_SIGNALS[signal_idx]

    logs = generate_log_batch(
        scenario_signals=signals,
        step=step,
        base_time=base_time,
        noise_ratio=GROUND_TRUTH["noise_ratio"],
        batch_size=8,
        rng=rng,
    )
    system_state = get_system_state(step, base_time)
    return logs, system_state


def get_active_alerts(step: int) -> list[str]:
    """Return active alerts for this step."""
    alerts = ["payment-service: circuit breaker OPEN", "payment-service: health check FAILING"]
    if step >= 2:
        alerts.append("SLA_BREACH: payment availability < 99.9%")
    if step >= 5:
        alerts.append("CRITICAL: payment-service DOWN > 150s")
    return alerts
```

---

## Step 3 — Write `server/environment.py`

This is the core class. It wires log_generator + scenarios into a proper OpenEnv environment.
Open `server/environment.py` and paste:

```python
"""
Core LogTriageEnvironment class.
Implements OpenEnv interface: reset(), step(), state property.
"""
from __future__ import annotations
import random
from datetime import datetime
from uuid import uuid4

from server.models import (
    TriageAction,
    TriageObservation,
    EpisodeState,
    LogLine,
    ServiceStatus,
)
from server.scenarios import single_crash
from server.log_generator import generate_healthy_system_state, _make_timestamp

# ─── TASK REGISTRY ─────────────────────────────────────────────────────────────

TASK_MAX_STEPS = {
    "single_crash":      8,
    "cascading_failure": 12,
    "silent_degradation": 15,
}

# ─── REWARD CONSTANTS ──────────────────────────────────────────────────────────

R_CORRECT_SEVERITY     =  0.30
R_CORRECT_ROOT_CAUSE   =  0.35
R_CORRECT_REMEDIATION  =  0.25
R_CORRECT_ESCALATION   =  0.10
R_SPEED_BONUS          =  0.10
R_PARTIAL_SERVICE_FAM  =  0.10
R_PARTIAL_SEVERITY_ADJ =  0.10

P_WRONG_ESCALATION     = -0.10
P_IGNORE_P1            = -0.50
P_REDUNDANT_ACTION     = -0.05
P_EXCEEDED_BUDGET      = -0.20
P_OVERESCALATE_P3_P1   = -0.15


class LogTriageEnvironment:
    """
    OpenEnv-compatible environment for SRE incident triage.

    Usage:
        env = LogTriageEnvironment()
        obs = env.reset(task_id="single_crash", seed=42)
        while not obs.done:
            action = agent.act(obs)
            obs = env.step(action)
        score = env.get_grader_score()
    """

    def __init__(self):
        self._state: EpisodeState | None = None
        self._rng: random.Random = random.Random()
        self._base_time: datetime = datetime.utcnow()
        self._task_id: str = "single_crash"
        self._ground_truth: dict = {}
        self._current_obs: TriageObservation | None = None

    # ─── OPENENV INTERFACE ─────────────────────────────────────────────────────

    def reset(self, task_id: str = "single_crash", seed: int | None = None) -> TriageObservation:
        """Start a fresh episode. Returns initial observation."""
        if task_id not in TASK_MAX_STEPS:
            raise ValueError(f"Unknown task_id '{task_id}'. Valid: {list(TASK_MAX_STEPS.keys())}")

        self._task_id = task_id
        self._rng = random.Random(seed)
        self._base_time = datetime.utcnow()

        # Load ground truth for this task
        if task_id == "single_crash":
            self._ground_truth = single_crash.GROUND_TRUTH
        else:
            # Tasks 2 & 3 will be wired in Day 3
            self._ground_truth = {}

        # Initialize episode state
        self._state = EpisodeState(
            episode_id=str(uuid4()),
            task_id=task_id,
            step_count=0,
            max_steps=TASK_MAX_STEPS[task_id],
            done=False,
            cumulative_score=0.0,
            actions_taken=[],
            correct_severity=None,
            correct_root_cause=None,
            correct_remediation=False,
        )

        # Get initial observation (step 0)
        logs, system_state = self._get_step_data(0)
        alerts = self._get_alerts(0)

        obs = TriageObservation(
            logs=logs,
            system_state=system_state,
            incident_id=self._state.episode_id,
            task_id=task_id,
            step_count=0,
            time_elapsed_seconds=0,
            active_alerts=alerts,
            reward=0.0,
            cumulative_score=0.0,
            done=False,
            last_action_feedback="Incident detected. Analyze the logs and take action.",
            invalid_action_error=None,
        )
        self._current_obs = obs
        return obs

    def step(self, action: TriageAction) -> TriageObservation:
        """Take one action. Returns next observation + reward."""
        if self._state is None:
            raise RuntimeError("Call reset() before step()")
        if self._state.done:
            raise RuntimeError("Episode is done. Call reset() to start a new episode.")

        # Validate action
        valid, err = action.is_valid()
        if not valid:
            return self._make_obs(
                reward=0.0,
                feedback=f"Invalid action: {err}",
                invalid_action_error=err,
                advance_step=False,
            )

        # Calculate reward for this action
        reward, feedback = self._evaluate_action(action)

        # Update state
        self._state.cumulative_score = round(
            self._state.cumulative_score + reward, 4
        )
        self._state.actions_taken.append(action.action_type)
        self._state.step_count += 1

        # Check if episode should end
        done = self._check_done(action)
        self._state.done = done

        # If done due to budget exceeded, apply penalty
        if self._state.step_count >= self._state.max_steps and not done:
            self._state.cumulative_score = round(
                self._state.cumulative_score + P_EXCEEDED_BUDGET, 4
            )
            self._state.done = True
            feedback += f" Step budget exceeded ({self._state.max_steps} steps). Penalty applied."

        return self._make_obs(reward=reward, feedback=feedback, advance_step=True)

    @property
    def state(self) -> EpisodeState:
        """Return current episode state."""
        if self._state is None:
            raise RuntimeError("Call reset() first.")
        return self._state

    def get_grader_score(self) -> float:
        """
        Return final grader score for the completed episode.
        Score is normalized to [0.0, 1.0].
        """
        if self._state is None:
            return 0.0
        # Clamp score to [0.0, 1.0]
        raw = self._state.cumulative_score
        return round(max(0.0, min(1.0, raw)), 4)

    # ─── INTERNAL HELPERS ──────────────────────────────────────────────────────

    def _evaluate_action(self, action: TriageAction) -> tuple[float, str]:
        """
        Evaluate the action against ground truth.
        Returns (reward: float, feedback: str).
        """
        gt = self._ground_truth
        reward = 0.0
        feedback_parts = []

        # Penalize redundant actions
        if action.action_type in self._state.actions_taken:
            reward += P_REDUNDANT_ACTION
            feedback_parts.append("Redundant action — you've already done this.")

        # ── classify_severity ──────────────────────────────────────────────────
        if action.action_type == "classify_severity":
            correct_sev = gt.get("severity", "")
            if action.value == correct_sev:
                if self._state.correct_severity is None:  # only reward first time
                    reward += R_CORRECT_SEVERITY
                    feedback_parts.append(f"Correct severity: {action.value}. +{R_CORRECT_SEVERITY}")
                    self._state.correct_severity = action.value
            else:
                # Partial credit: P1 vs P2 is close, P1 vs P3 is not
                if correct_sev == "P1" and action.value == "P3":
                    reward += P_OVERESCALATE_P3_P1  # wrong direction
                    feedback_parts.append(f"Incorrect severity: {action.value}. P1 expected. This is a customer-impacting incident.")
                elif correct_sev == "P1" and action.value == "P2":
                    reward += R_PARTIAL_SEVERITY_ADJ
                    feedback_parts.append(f"Close — {action.value} given, P1 expected. Partial credit.")
                else:
                    feedback_parts.append(f"Incorrect severity: {action.value}. Reassess.")

        # ── identify_root_cause ────────────────────────────────────────────────
        elif action.action_type == "identify_root_cause":
            correct_rc = gt.get("root_cause", "")
            if action.value == correct_rc:
                if self._state.correct_root_cause is None:
                    reward += R_CORRECT_ROOT_CAUSE
                    feedback_parts.append(f"Correct root cause: {action.value}. +{R_CORRECT_ROOT_CAUSE}")
                    self._state.correct_root_cause = action.value
            else:
                # Partial credit: same tier (e.g. payment-db instead of payment-service)
                if correct_rc.split("-")[0] == action.value.split("-")[0]:
                    reward += R_PARTIAL_SERVICE_FAM
                    feedback_parts.append(f"Close — {action.value} is in the right service family. Check more carefully.")
                else:
                    feedback_parts.append(f"Incorrect root cause: {action.value}. Look at which service is actually failing.")

        # ── escalate ──────────────────────────────────────────────────────────
        elif action.action_type == "escalate":
            correct_teams = gt.get("correct_teams", set())
            if action.value in correct_teams:
                reward += R_CORRECT_ESCALATION
                feedback_parts.append(f"Correct escalation to {action.value}. +{R_CORRECT_ESCALATION}")
            else:
                reward += P_WRONG_ESCALATION
                feedback_parts.append(f"Wrong team escalated: {action.value}. Penalty applied.")

        # ── remediate ─────────────────────────────────────────────────────────
        elif action.action_type == "remediate":
            prefix = action.value.split(":")[0]
            service = action.value.split(":")[1] if ":" in action.value else ""
            correct_prefixes = gt.get("remediation_prefixes", set())
            correct_service = gt.get("remediation_service", "")

            if prefix in correct_prefixes and service == correct_service:
                if not self._state.correct_remediation:
                    reward += R_CORRECT_REMEDIATION
                    feedback_parts.append(f"Correct remediation: {action.value}. +{R_CORRECT_REMEDIATION}")
                    self._state.correct_remediation = True
            elif service == correct_service and prefix not in correct_prefixes:
                reward += 0.05  # right service, wrong action
                feedback_parts.append(f"Right service, but '{prefix}' may not fix this. Try another remediation type.")
            else:
                feedback_parts.append(f"Incorrect remediation: {action.value}. Reconsider which service needs fixing.")

        # ── ignore ────────────────────────────────────────────────────────────
        elif action.action_type == "ignore":
            correct_sev = gt.get("severity", "")
            if correct_sev == "P1":
                reward += P_IGNORE_P1
                feedback_parts.append(f"CRITICAL ERROR: Ignored a P1 incident! Major penalty applied.")
            else:
                feedback_parts.append("Marked as noise.")

        # ── request_more_logs ─────────────────────────────────────────────────
        elif action.action_type == "request_more_logs":
            feedback_parts.append(f"Fetching more logs for {action.value}...")

        # ── resolve ───────────────────────────────────────────────────────────
        elif action.action_type == "resolve":
            # Speed bonus if resolved within 60% of step budget
            step_budget = self._state.max_steps
            if self._state.step_count <= int(step_budget * 0.6):
                reward += R_SPEED_BONUS
                feedback_parts.append(f"Incident resolved efficiently. Speed bonus: +{R_SPEED_BONUS}")
            else:
                feedback_parts.append("Incident resolved.")

        return round(reward, 4), " | ".join(feedback_parts) or "Action processed."

    def _check_done(self, action: TriageAction) -> bool:
        """Episode ends on resolve, ignore (with P1), or step budget exhausted."""
        if action.action_type == "resolve":
            return True
        if action.action_type == "ignore" and self._ground_truth.get("severity") == "P1":
            return True  # Catastrophic — episode ends immediately
        if self._state.step_count >= self._state.max_steps:
            return True
        return False

    def _get_step_data(self, step: int):
        """Get logs and system state for the current step."""
        if self._task_id == "single_crash":
            return single_crash.get_step_data(step, self._base_time, self._rng)
        # Tasks 2 & 3 wired in Day 3
        return [], generate_healthy_system_state(self._base_time)

    def _get_alerts(self, step: int) -> list[str]:
        """Get active alerts for the current step."""
        if self._task_id == "single_crash":
            return single_crash.get_active_alerts(step)
        return []

    def _make_obs(
        self,
        reward: float,
        feedback: str,
        invalid_action_error: str | None = None,
        advance_step: bool = True,
    ) -> TriageObservation:
        """Build a TriageObservation for the current state."""
        step = self._state.step_count
        logs, system_state = self._get_step_data(step)
        alerts = self._get_alerts(step)

        return TriageObservation(
            logs=logs,
            system_state=system_state,
            incident_id=self._state.episode_id,
            task_id=self._state.task_id,
            step_count=step,
            time_elapsed_seconds=step * 30,
            active_alerts=alerts,
            reward=reward,
            cumulative_score=self._state.cumulative_score,
            done=self._state.done,
            last_action_feedback=feedback,
            invalid_action_error=invalid_action_error,
        )
```

---

## Step 4 — Wire `app.py` Endpoints

Now replace the placeholder `/reset`, `/step`, and `/state` endpoints in `server/app.py`.

**Replace the entire file** with this:

```python
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn

from server.models import TriageAction
from server.environment import LogTriageEnvironment

app = FastAPI(
    title="LogTriageEnv",
    description="OpenEnv environment for SRE incident triage",
    version="1.0.0",
)

# One environment instance per server process
# (In production / HF Spaces, each request could get its own instance)
env = LogTriageEnvironment()


@app.get("/health")
def health():
    return {"status": "ok", "environment": "logtriage-env", "version": "1.0.0"}


@app.post("/reset")
def reset(
    task: str = Query(default="single_crash", description="Task ID to run"),
    seed: int = Query(default=None, description="Random seed for reproducibility"),
):
    try:
        obs = env.reset(task_id=task, seed=seed)
        return obs.model_dump()
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/step")
def step(action: TriageAction):
    valid, err = action.is_valid()
    if not valid:
        return JSONResponse(status_code=422, content={"error": err})
    try:
        obs = env.step(action)
        return obs.model_dump()
    except RuntimeError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/state")
def state():
    try:
        return env.state.model_dump()
    except RuntimeError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


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
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "cascading_failure",
                "name": "Cascading Failure",
                "difficulty": "medium",
                "max_steps": 12,
                "description": "DB slowdown cascades upstream. Find the true root cause, not symptoms.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "silent_degradation",
                "name": "Silent Degradation with Noise",
                "difficulty": "hard",
                "max_steps": 15,
                "description": "Slow degradation hidden in 60% noise. Nuanced P2 severity judgment.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
        ]
    }


@app.post("/grader")
def grader():
    score = env.get_grader_score()
    return {
        "score": score,
        "episode_id": env.state.episode_id if env._state else None,
        "task_id": env._task_id,
        "steps_taken": env.state.step_count if env._state else 0,
    }


@app.post("/baseline")
def baseline():
    # TODO Day 5: wire to baseline.py
    return {"message": "baseline endpoint — to be wired on Day 5"}


if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=True)
```

---

## Step 5 — Test Full Episode End-to-End

### 5a. Start the server

```bash
cd C:\Users\Rohit\Desktop\logtriage-env
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

### 5b. Play a full Task 1 episode (open second terminal)

Run these curl commands **in order** — this simulates a correct agent solving Task 1:

```bash
# 1. Start episode
curl -X POST "http://localhost:7860/reset?task=single_crash&seed=42"

# 2. Classify severity correctly
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"classify_severity\", \"value\": \"P1\", \"confidence\": 0.95, \"reasoning\": \"error rate spike and circuit breaker open\"}"

# 3. Identify root cause correctly
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"identify_root_cause\", \"value\": \"payment-service\", \"confidence\": 0.9, \"reasoning\": \"NullPointerException in payment-service logs\"}"

# 4. Apply correct remediation
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"remediate\", \"value\": \"restart:payment-service\", \"confidence\": 0.85, \"reasoning\": \"NPE likely from bad deploy, restart clears it\"}"

# 5. Resolve the incident
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"resolve\", \"value\": \"resolved\", \"confidence\": 1.0, \"reasoning\": \"payment-service restarted and healthy\"}"

# 6. Check final grader score — should be ~0.9+
curl -X POST http://localhost:7860/grader

# 7. Check episode state
curl http://localhost:7860/state
```

**Expected final score:** 0.90–1.00
- classify_severity P1 correct: +0.30
- identify_root_cause payment-service correct: +0.35
- remediate restart:payment-service correct: +0.25
- resolve within 4 steps (well under 8): +0.10 speed bonus
- **Total: 1.00**

### 5c. Test a WRONG agent (should score lower)

```bash
# Reset fresh
curl -X POST "http://localhost:7860/reset?task=single_crash&seed=42"

# Wrong severity
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"classify_severity\", \"value\": \"P3\", \"confidence\": 0.5, \"reasoning\": \"seems minor\"}"

# Wrong root cause
curl -X POST http://localhost:7860/step ^
  -H "Content-Type: application/json" ^
  -d "{\"action_type\": \"identify_root_cause\", \"value\": \"api-gateway\", \"confidence\": 0.5, \"reasoning\": \"gateway errors visible\"}"

# Check score — should be much lower (or negative)
curl -X POST http://localhost:7860/grader
```

**This proves graders return VARYING scores — critical for disqualification avoidance.**

---

## Step 6 — Git Push

```bash
cd C:\Users\Rohit\Desktop\logtriage-env
git add .
git commit -m "Day 2: environment.py, log_generator.py, single_crash scenario, real endpoints

- LogTriageEnvironment with real reset()/step()/state()
- Reward function with partial credit + penalties
- log_generator.py — realistic log synthesis with signal/noise mixing
- single_crash.py — Task 1 scenario with 8-step signal progression
- /reset, /step, /state endpoints now return real observations
- Full Task 1 episode playable end-to-end
- Grader returns varying scores (proven with correct vs wrong agent)"

git push origin main
```

---

## Day 2 Done Checklist

- [ ] `server/log_generator.py` created — `generate_log_batch()` returns `list[LogLine]`
- [ ] `server/scenarios/single_crash.py` created — `GROUND_TRUTH`, `STEP_SIGNALS`, `get_step_data()`, `get_active_alerts()` all defined
- [ ] `server/environment.py` created — `LogTriageEnvironment` with `reset()`, `step()`, `state` property, `get_grader_score()`
- [ ] `server/app.py` updated — `/reset`, `/step`, `/state` return real data
- [ ] `uvicorn server.app:app` starts without errors
- [ ] `POST /reset?task=single_crash` returns real logs + system state (not placeholder text)
- [ ] `POST /step` with correct actions returns positive rewards
- [ ] `POST /step` with wrong actions returns negative/zero rewards
- [ ] `POST /grader` returns a score that varies between correct and wrong agents
- [ ] `GET /state` returns real episode state (step count, cumulative score, actions taken)
- [ ] Full correct episode scores 0.90+ on Task 1
- [ ] Full wrong episode scores differently (proves score variance)
- [ ] Git pushed

---

## What NOT to do today

- Do NOT start Tasks 2 or 3 scenarios (that is Day 3)
- Do NOT start grader files in `server/graders/` (that is Day 4)
- Do NOT touch HF Spaces or Docker beyond making sure it still builds
- Do NOT add complexity to reward function — the one above is final

---

## Tomorrow (Day 3 Preview)

You will write `server/scenarios/cascading.py` (Task 2) and `server/scenarios/silent_degrade.py` (Task 3), wire them into `environment.py`, and verify all 3 tasks produce real observations with the reward function working correctly across all scenarios.
