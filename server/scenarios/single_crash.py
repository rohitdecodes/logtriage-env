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
