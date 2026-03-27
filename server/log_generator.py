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
