"""
Grader for Task 1 — Single Service Crash (Easy)

Scoring breakdown:
  Correct severity (P1)                    → +0.30
  Correct root cause (payment-service)     → +0.35
  Correct remediation (restart:payment-*) → +0.25
  Speed bonus (resolved ≤ 5 steps)         → +0.10
  ─────────────────────────────────────────────────
  Maximum possible score                   →  1.00

Penalties:
  Ignored P1 incident                      → -0.30 (from base)
  Wrong root cause identified              →  0.00 (no credit)
  Never resolved                           → -0.10
"""
from __future__ import annotations
from server.models import EpisodeState
from server.graders.base_grader import BaseGrader


class CrashGrader(BaseGrader):
    """Official grader for Task 1 — Single Service Crash."""

    # Ground truth constants
    CORRECT_SEVERITY = "P1"
    CORRECT_ROOT_CAUSE = "payment-service"
    CORRECT_REMEDIATION_PREFIX = "restart"
    CORRECT_REMEDIATION_SERVICE = "payment-service"
    MAX_STEPS = 8
    SPEED_THRESHOLD = 5  # must resolve within this many steps for speed bonus

    def score(self, state: EpisodeState) -> float:
        """
        Score the completed Task 1 episode.
        Deterministic — same action history always produces same score.
        """
        total = 0.0
        breakdown = {}

        # ── 1. Severity classification ─────────────────────────────────────────
        severity_value = self._get_first_value(state, "classify_severity")
        if severity_value == self.CORRECT_SEVERITY:
            total += 0.30
            breakdown["severity"] = "+0.30 (correct: P1)"
        elif severity_value == "P2":
            total += 0.10  # partial credit — close but not right
            breakdown["severity"] = "+0.10 (partial: P2 given, P1 expected)"
        elif severity_value is None:
            breakdown["severity"] = "+0.00 (never classified)"
        else:
            breakdown["severity"] = f"+0.00 (wrong: {severity_value})"

        # ── 2. Root cause identification ───────────────────────────────────────
        root_cause_value = self._get_first_value(state, "identify_root_cause")
        if root_cause_value == self.CORRECT_ROOT_CAUSE:
            total += 0.35
            breakdown["root_cause"] = "+0.35 (correct: payment-service)"
        elif root_cause_value and root_cause_value.startswith("payment"):
            total += 0.10  # partial — right service family
            breakdown["root_cause"] = f"+0.10 (partial: {root_cause_value}, right family)"
        elif root_cause_value is None:
            breakdown["root_cause"] = "+0.00 (never identified)"
        else:
            breakdown["root_cause"] = f"+0.00 (wrong: {root_cause_value})"

        # ── 3. Remediation ─────────────────────────────────────────────────────
        remediation_actions = self._get_actions_of_type(state, "remediate")
        remediation_scored = False
        for action in remediation_actions:
            value = action.get("value", "")
            parts = value.split(":")
            if len(parts) == 2:
                prefix, service = parts
                if prefix == self.CORRECT_REMEDIATION_PREFIX and service == self.CORRECT_REMEDIATION_SERVICE:
                    total += 0.25
                    breakdown["remediation"] = f"+0.25 (correct: {value})"
                    remediation_scored = True
                    break
                elif service == self.CORRECT_REMEDIATION_SERVICE:
                    total += 0.08  # right service, wrong action type
                    breakdown["remediation"] = f"+0.08 (partial: right service, wrong action)"
                    remediation_scored = True
                    break

        if not remediation_scored:
            breakdown["remediation"] = "+0.00 (no correct remediation)"

        # ── 4. Speed bonus ─────────────────────────────────────────────────────
        if self._episode_resolved(state):
            if self._steps_used(state) <= self.SPEED_THRESHOLD:
                total += 0.10
                breakdown["speed"] = f"+0.10 (resolved in {self._steps_used(state)} steps)"
            else:
                breakdown["speed"] = f"+0.00 (resolved but slow: {self._steps_used(state)} steps)"
        else:
            total -= 0.10  # penalty for not resolving
            breakdown["resolution"] = "-0.10 (never resolved)"

        # ── 5. Ignore penalty ──────────────────────────────────────────────────
        if self._was_action_taken(state, "ignore"):
            total -= 0.30
            breakdown["ignore_penalty"] = "-0.30 (ignored P1 incident)"

        self._breakdown = breakdown
        return self._clamp(total)

    def get_breakdown(self) -> dict:
        """Return scoring breakdown from last score() call."""
        return getattr(self, "_breakdown", {})
