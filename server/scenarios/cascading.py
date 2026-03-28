"""
Task 2 — Cascading Failure (Medium)

Scenario: user-db develops a slow query that exhausts the auth-service connection pool,
which then causes the api-gateway to return timeouts to all users.

Surface logs show gateway errors most loudly (symptom), but root cause is hidden (user-db).
Agent must trace backward through the cascade chain — NOT treat symptoms as root cause.

Ground truth:
  - severity: P1
  - root_cause: user-db
  - remediation: kill-query:user-db OR restart:user-db
  - correct_teams: dba-team, sre-team
  - noise_ratio: 30%
"""
from __future__ import annotations
import random
from datetime import datetime
from server.models import LogLine, ServiceStatus
from server.log_generator import (
    generate_log_batch,
    generate_healthy_system_state,
    _make_timestamp,
)

# ─── GROUND TRUTH ─────────────────────────────────────────────────────────────

GROUND_TRUTH = {
    "severity": "P1",
    "root_cause": "user-db",
    "remediation_prefixes": {"kill-query", "restart"},
    "remediation_service": "user-db",
    "correct_teams": {"dba-team", "sre-team"},
    "max_steps": 12,
    "noise_ratio": 0.30,
}

# ─── STEP-BY-STEP SIGNAL PLAN ─────────────────────────────────────────────────
# Cascade chain: user-db slow query → auth-service pool exhausted → api-gateway timeouts
# Steps 0-1: Gateway errors surface (symptoms only — most visible)
# Steps 2-3: Auth-service DB pressure becomes visible
# Steps 4-5: user-db slow queries exposed; circuit breaker opens
# Steps 6-7: Full cascade — all 3 services degraded/down
# Steps 8-11: Escalating alerts; root cause becomes unmistakable

STEP_SIGNALS = [
    # Step 0: Gateway errors first to appear (surface symptom)
    [
        ("api-gateway", "ERROR", "upstream timeout from auth-service: 5002ms"),
        ("api-gateway", "WARN",  "error rate: 8.3% on /auth/* routes"),
    ],
    # Step 1: More gateway errors; first hints of auth-service pressure
    [
        ("api-gateway", "ERROR", "upstream timeout from auth-service: 30007ms"),
        ("api-gateway", "WARN",  "error rate: 15.7% — auth-service latency climbing"),
    ],
    # Step 2: Auth-service connection pool pressure visible
    [
        ("auth-service", "WARN",  "db connection pool at 42/50 — pressure building"),
        ("api-gateway",  "ERROR", "upstream timeout from auth-service: 30005ms"),
        ("auth-service", "ERROR", "db query timeout: SELECT session WHERE user_id=? [5001ms]"),
    ],
    # Step 3: Auth-service pool nearly exhausted
    [
        ("auth-service", "ERROR", "db connection pool EXHAUSTED (50/50) — blocking new requests"),
        ("api-gateway",  "ERROR", "auth-service unavailable: connection pool full"),
        ("auth-service", "WARN",  "request queue depth: 127 — approaching overflow"),
    ],
    # Step 4: user-db slow query finally exposed
    [
        ("user-db",      "WARN",  "slow query detected: SELECT * FROM sessions WHERE user_id=? [2847ms]"),
        ("auth-service", "ERROR", "db connection timeout after 5000ms — query hanging"),
        ("user-db",      "ERROR", "lock wait timeout: session table — blocking reads"),
    ],
    # Step 5: user-db circuit breaker opens; auth-service starts failing fast
    [
        ("user-db",      "WARN",  "slow query: 4500ms — circuit breaker approaching threshold"),
        ("auth-service", "ERROR", "circuit breaker OPEN for user-db: latency exceeded 5000ms"),
        ("api-gateway",  "ERROR", "all /auth/* requests failing — upstream unavailable"),
    ],
    # Step 6: Full cascade — all 3 services degraded
    [
        ("api-gateway",  "ERROR", "error rate: 67.4% — multiple upstreams timing out"),
        ("auth-service", "ERROR", "health check FAILED: cannot reach user-db"),
        ("user-db",      "ERROR", "connection pool saturated: 95/100 connections in use"),
    ],
    # Step 7: api-gateway now fully symptomatic
    [
        ("api-gateway",  "FATAL", "SLA breach: /auth endpoint availability < 95%"),
        ("auth-service", "ERROR", "auth-service DOWN: 3/3 health checks failed"),
        ("user-db",      "WARN",  "slow query count: 847 in last 60s — severe degradation"),
    ],
    # Step 8: Database fully exposed as root cause
    [
        ("user-db",      "ERROR", "CRITICAL: user-db query latency 8000ms+ — active sessions timing out"),
        ("auth-service", "ERROR", "rejected: user-db connection pool exhausted"),
        ("api-gateway",  "ERROR", "user-auth endpoint returning 503 — cascade failure"),
    ],
    # Step 9: Escalating
    [
        ("user-db",      "FATAL", "user-db DOWN: connection pool 100/100 — no connections available"),
        ("api-gateway",  "ERROR", "error rate: 89.2% — auth-service and user-db both unreachable"),
    ],
    # Step 10: Critical
    [
        ("api-gateway",  "FATAL", "CRITICAL: auth-service DOWN for 90s — 100% of login attempts failing"),
        ("user-db",      "ERROR", "lock contention: session table fully locked — queries timing out"),
    ],
    # Step 11: Maximum severity
    [
        ("user-db",      "FATAL", "user-db unresponsive for 180s — database crisis"),
        ("api-gateway",  "FATAL", "SLA_BREACH: auth availability 0% — complete user-auth outage"),
    ],
]


def get_system_state(step: int, base_time: datetime) -> dict[str, ServiceStatus]:
    """Return system state for this step. Cascade: user-db → auth-service → api-gateway."""
    now = _make_timestamp(base_time, step * 30)
    state = generate_healthy_system_state(base_time)

    # Escalating degradation based on step
    if step <= 1:
        # Gateway just starting to see issues
        state["api-gateway"] = ServiceStatus(
            name="api-gateway", status="degraded", error_rate=0.083, latency_p99_ms=2500, last_updated=now
        )
    elif step <= 3:
        # Auth-service pool pressure
        state["api-gateway"] = ServiceStatus(
            name="api-gateway", status="degraded", error_rate=0.157, latency_p99_ms=5000, last_updated=now
        )
        state["auth-service"] = ServiceStatus(
            name="auth-service", status="degraded", error_rate=0.15, latency_p99_ms=5000, last_updated=now
        )
    elif step <= 5:
        # user-db slow queries exposed
        state["api-gateway"] = ServiceStatus(
            name="api-gateway", status="degraded", error_rate=0.45, latency_p99_ms=8000, last_updated=now
        )
        state["auth-service"] = ServiceStatus(
            name="auth-service", status="down", error_rate=0.85, latency_p99_ms=10000, last_updated=now
        )
        state["user-db"] = ServiceStatus(
            name="user-db", status="degraded", error_rate=0.30, latency_p99_ms=4500, last_updated=now
        )
    elif step <= 7:
        # Full cascade
        state["api-gateway"] = ServiceStatus(
            name="api-gateway", status="down", error_rate=0.89, latency_p99_ms=10000, last_updated=now
        )
        state["auth-service"] = ServiceStatus(
            name="auth-service", status="down", error_rate=0.95, latency_p99_ms=10000, last_updated=now
        )
        state["user-db"] = ServiceStatus(
            name="user-db", status="down", error_rate=0.50, latency_p99_ms=8000, last_updated=now
        )
    else:
        # Maximum severity
        state["api-gateway"] = ServiceStatus(
            name="api-gateway", status="down", error_rate=0.99, latency_p99_ms=10000, last_updated=now
        )
        state["auth-service"] = ServiceStatus(
            name="auth-service", status="down", error_rate=1.0, latency_p99_ms=10000, last_updated=now
        )
        state["user-db"] = ServiceStatus(
            name="user-db", status="down", error_rate=0.75, latency_p99_ms=10000, last_updated=now
        )

    return state


def get_step_data(step: int, base_time: datetime, rng: random.Random) -> tuple[list[LogLine], dict[str, ServiceStatus]]:
    """
    Returns (logs, system_state) for the given step.
    Signal gets louder over time if agent hasn't acted.
    """
    signal_idx = min(step, len(STEP_SIGNALS) - 1)
    signals = STEP_SIGNALS[signal_idx]

    logs = generate_log_batch(
        scenario_signals=signals,
        step=step,
        base_time=base_time,
        noise_ratio=GROUND_TRUTH["noise_ratio"],
        batch_size=10,
        rng=rng,
    )
    system_state = get_system_state(step, base_time)
    return logs, system_state


def get_active_alerts(step: int) -> list[str]:
    """Return active alerts for this step."""
    alerts = []
    if step >= 0:
        alerts.append("api-gateway: elevated error rate on /auth/* routes")
    if step >= 2:
        alerts.append("auth-service: db connection pool pressure")
    if step >= 4:
        alerts.append("user-db: slow queries detected — latency 2000ms+")
    if step >= 5:
        alerts.append("auth-service: circuit breaker OPEN for user-db")
    if step >= 6:
        alerts.append("SLA_BREACH: /auth availability < 90%")
    if step >= 8:
        alerts.append("CRITICAL: user-db connection pool saturated")
    if step >= 10:
        alerts.append("CRITICAL: full auth cascade failure — P1 incident")
    return alerts
