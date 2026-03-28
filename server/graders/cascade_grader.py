"""
Grader for Task 2 — Cascading Failure (Medium)

Scoring breakdown:
  Correct severity (P1)                    → +0.20
  Correct root cause (user-db)             → +0.35
  Correct remediation (kill-query/restart) → +0.25
  Ordering bonus (no symptom fix first)    → +0.10
  Speed bonus (resolved ≤ 8 steps)         → +0.10
  ─────────────────────────────────────────────────
  Maximum possible score                   →  1.00

Penalties:
  Identified symptom as root cause         →  0.00 (no credit)
  Remediated symptom service first         → -0.10 (ordering penalty)
  Never resolved                           → -0.10
"""
from __future__ import annotations
from server.models import EpisodeState
from server.graders.base_grader import BaseGrader


class CascadeGrader(BaseGrader):
    """Official grader for Task 2 — Cascading Failure."""

    CORRECT_SEVERITY = "P1"
    CORRECT_ROOT_CAUSE = "user-db"
    CORRECT_REMEDIATION_PREFIXES = {"kill-query", "restart"}
    CORRECT_REMEDIATION_SERVICE = "user-db"
    SYMPTOM_SERVICES = {"api-gateway", "auth-service"}  # wrong answers
    MAX_STEPS = 12
    SPEED_THRESHOLD = 8

    def score(self, state: EpisodeState) -> float:
        """
        Score the completed Task 2 episode.
        Penalizes agents that treat symptoms instead of root cause.
        """
        total = 0.0
        breakdown = {}

        # ── 1. Severity classification ─────────────────────────────────────────
        severity_value = self._get_first_value(state, "classify_severity")
        if severity_value == self.CORRECT_SEVERITY:
            total += 0.20
            breakdown["severity"] = "+0.20 (correct: P1)"
        elif severity_value == "P2":
            total += 0.08
            breakdown["severity"] = "+0.08 (partial: P2 given, P1 expected)"
        elif severity_value is None:
            breakdown["severity"] = "+0.00 (never classified)"
        else:
            breakdown["severity"] = f"+0.00 (wrong: {severity_value})"

        # ── 2. Root cause identification ───────────────────────────────────────
        root_cause_value = self._get_first_value(state, "identify_root_cause")
        if root_cause_value == self.CORRECT_ROOT_CAUSE:
            total += 0.35
            breakdown["root_cause"] = "+0.35 (correct: user-db)"
        elif root_cause_value in self.SYMPTOM_SERVICES:
            # Identified a symptom, not root cause — no credit
            breakdown["root_cause"] = f"+0.00 (wrong: {root_cause_value} is a symptom, not root cause)"
        elif root_cause_value and "db" in root_cause_value:
            total += 0.10  # right tier (database), wrong specific service
            breakdown["root_cause"] = f"+0.10 (partial: {root_cause_value}, right tier)"
        elif root_cause_value is None:
            breakdown["root_cause"] = "+0.00 (never identified)"
        else:
            breakdown["root_cause"] = f"+0.00 (wrong: {root_cause_value})"

        # ── 3. Remediation + Ordering ──────────────────────────────────────────
        remediation_actions = self._get_actions_of_type(state, "remediate")
        remediation_scored = False
        symptom_remediated_first = False

        for i, action in enumerate(remediation_actions):
            value = action.get("value", "")
            parts = value.split(":")
            if len(parts) != 2:
                continue
            prefix, service = parts

            # Check if agent remediated a symptom service before root cause
            if service in self.SYMPTOM_SERVICES and not remediation_scored:
                symptom_remediated_first = True

            # Check for correct remediation
            if (
                prefix in self.CORRECT_REMEDIATION_PREFIXES
                and service == self.CORRECT_REMEDIATION_SERVICE
                and not remediation_scored
            ):
                total += 0.25
                breakdown["remediation"] = f"+0.25 (correct: {value})"
                remediation_scored = True

        if not remediation_scored:
            breakdown["remediation"] = "+0.00 (no correct remediation)"

        # ── 4. Ordering bonus ──────────────────────────────────────────────────
        if not symptom_remediated_first and remediation_scored:
            total += 0.10
            breakdown["ordering"] = "+0.10 (correctly targeted root cause, not symptoms)"
        elif symptom_remediated_first:
            total -= 0.10
            breakdown["ordering"] = "-0.10 (remediated symptom service before root cause)"

        # ── 5. Speed bonus ─────────────────────────────────────────────────────
        if self._episode_resolved(state):
            if self._steps_used(state) <= self.SPEED_THRESHOLD:
                total += 0.10
                breakdown["speed"] = f"+0.10 (resolved in {self._steps_used(state)} steps)"
            else:
                breakdown["speed"] = f"+0.00 (resolved but used {self._steps_used(state)} steps)"
        else:
            total -= 0.10
            breakdown["resolution"] = "-0.10 (never resolved)"

        self._breakdown = breakdown
        return self._clamp(total)

    def get_breakdown(self) -> dict:
        return getattr(self, "_breakdown", {})
