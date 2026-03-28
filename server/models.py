from __future__ import annotations
from typing import Literal, Optional, ClassVar
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
    VALID_SEVERITIES: ClassVar = {"P1", "P2", "P3"}
    VALID_SERVICES: ClassVar = {
        "api-gateway",
        "auth-service",
        "user-db",
        "payment-service",
        "payment-db",
        "notification-service",
        "email-queue",
    }
    VALID_TEAMS: ClassVar = {
        "sre-team",
        "backend-team",
        "dba-team",
        "security-team",
    }
    VALID_REMEDIATION_PREFIXES: ClassVar = {
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
    action_history: list[dict] = Field(
        default_factory=list,
        description="Full action objects taken this episode (for grader evaluation)"
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
