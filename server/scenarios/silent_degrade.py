"""
Task 3 — Silent Degradation with Noise (Hard)

Scenario: payment-db query latency slowly increases over time.
No service crashes. Error rate stays below P1 threshold (5%).
60% of logs are irrelevant noise from unrelated services.
Agent must filter noise, identify subtle signal, classify as P2 (NOT P1, NOT P3).

Ground truth:
  - severity: P2 (nuanced — trending toward breach but no hard outage yet)
  - root_cause: payment-db
  - remediation: flush-cache:payment-db OR kill-query:payment-db
  - correct_teams: dba-team
  - noise_ratio: 60% (hardest noise ratio of all tasks)
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

# Ground Truth

GROUND_TRUTH = {
    "severity": "P2",
    "root_cause": "payment-db",
    "remediation_prefixes": {"flush-cache", "kill-query"},
    "remediation_service": "payment-db",
    "correct_teams": {"dba-team"},
    "max_steps": 15,
    "noise_ratio": 0.60,
}

# Step signals: (service, level, message)
STEP_SIGNALS = [
    # Step 0: Very subtle
    [("payment-db", "WARN", "payment-db: query latency elevated 450ms (baseline: 12ms)")],
    # Step 1
    [("payment-db", "WARN", "payment-db: query latency 620ms")],
    # Step 2
    [("payment-db", "WARN", "payment-db: slow query: SELECT * FROM transactions WHERE user_id=? [890ms]")],
    # Step 3
    [("payment-db", "WARN", "payment-db: buffer cache hit ratio dropping: 89% to 71%")],
    # Step 4
    [("payment-db", "WARN", "payment-db: query latency 1200ms"), ("payment-service", "WARN", "payment-service: error rate 2.1%")],
    # Step 5
    [("payment-db", "WARN", "payment-db: buffer cache hit ratio 54% — cache thrashing")],
    # Step 6
    [("payment-db", "WARN", "payment-db: slow query: SELECT * FROM transactions [2200ms]")],
    # Step 7
    [("payment-db", "WARN", "payment-db: query latency 2800ms"), ("payment-service", "ERROR", "payment-service: 3.4% error rate")],
    # Step 8
    [("payment-db", "ERROR", "payment-db: slow query timeout: [3100ms] — query cancelled")],
    # Step 9
    [("payment-db", "WARN", "payment-db: query latency 4200ms — cache fully cold")],
    # Step 10
    [("payment-db", "ERROR", "payment-db: query latency 4500ms")],
    # Step 11
    [("payment-db", "WARN", "payment-db: buffer pool pages: 94% dirty")],
    # Step 12
    [("payment-db", "ERROR", "payment-db: query latency 4600ms — timeouts beginning"), ("payment-service", "ERROR", "payment-service: error rate 4.9%")],
    # Step 13: P1 breached
    [("payment-db", "ERROR", "payment-db: CRITICAL query latency 4950ms — P1 breached"), ("payment-service", "ERROR", "payment-service: error rate 5.1% — P1 exceeded")],
    # Step 14: Worst case
    [("payment-db", "FATAL", "payment-db: query latency 5000ms+ — connection pool exhausted"), ("payment-service", "FATAL", "payment-service: P1 CRITICAL — 6.2% error rate")],
]


def get_system_state(step: int, base_time: datetime) -> dict[str, ServiceStatus]:
    now = _make_timestamp(base_time, step * 30)
    state = generate_healthy_system_state(base_time)

    latencies = [450, 620, 890, 1200, 1400, 1800, 2200, 2800, 3100, 4200, 4500, 4600, 4600, 4950, 5000]
    error_rates = [0.0, 0.005, 0.01, 0.021, 0.021, 0.025, 0.028, 0.034, 0.038, 0.042, 0.047, 0.049, 0.049, 0.051, 0.062]

    step_idx = min(step, len(latencies) - 1)
    db_latency = latencies[step_idx]
    db_error = error_rates[step_idx]

    psvc_latency = min(5000, 340 + db_latency // 2)
    psvc_error = min(0.10, db_error * 0.8)

    state["payment-db"] = ServiceStatus(
        name="payment-db",
        status="up" if step < 3 else "degraded",
        error_rate=db_error,
        latency_p99_ms=db_latency,
        last_updated=now,
    )
    state["payment-service"] = ServiceStatus(
        name="payment-service",
        status="degraded" if step >= 4 else "up",
        error_rate=psvc_error,
        latency_p99_ms=psvc_latency,
        last_updated=now,
    )
    return state


def get_step_data(step: int, base_time: datetime, rng: random.Random) -> tuple[list[LogLine], dict[str, ServiceStatus]]:
    signal_idx = min(step, len(STEP_SIGNALS) - 1)
    signals = STEP_SIGNALS[signal_idx]

    logs = generate_log_batch(
        scenario_signals=signals,
        step=step,
        base_time=base_time,
        noise_ratio=GROUND_TRUTH["noise_ratio"],
        batch_size=12,
        rng=rng,
    )
    system_state = get_system_state(step, base_time)
    return logs, system_state


def get_active_alerts(step: int) -> list[str]:
    alerts = []
    if step >= 4:
        alerts.append("payment-service: error rate 2%+ — watching")
    if step >= 6:
        alerts.append("payment-service: p99 latency above threshold")
    if step >= 9:
        alerts.append("payment-db: query latency 4000ms+ — approaching P1 threshold")
    if step >= 12:
        alerts.append("WARNING: payment error rate approaching 5% P1 threshold")
    if step >= 13:
        alerts.append("ALERT: P1 threshold BREACHED for payment-service")
    return alerts
