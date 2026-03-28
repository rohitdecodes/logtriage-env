"""
Grader for Task 3 — Silent Degradation with Noise (Hard)

Scoring breakdown:
  Correct severity (P2)                      → +0.30
  Correct root cause (payment-db)            → +0.30
  Correct remediation (flush-cache/kill-q)   → +0.20
  No spurious actions on noise services      → +0.10
  Speed bonus (resolved ≤ 10 steps)          → +0.10
  ──────────────────────────────────────────────────
  Maximum possible score                     →  1.00

Penalties:
  Over-escalation (classified P1)            → -0.15
  Under-escalation (classified P3)           → -0.15
  Remediated wrong service                   →  0.00 (no credit)
  Never resolved/escalated                   → -0.10
"""
from __future__ import annotations
from server.models import EpisodeState
from server.graders.base_grader import BaseGrader


class NoiseGrader(BaseGrader):
    """Official grader for Task 3 — Silent Degradation with Noise."""

    CORRECT_SEVERITY = "P2"
    CORRECT_ROOT_CAUSE = "payment-db"
    CORRECT_REMEDIATION_PREFIXES = {"flush-cache", "kill-query"}
    CORRECT_REMEDIATION_SERVICE = "payment-db"
    CORRECT_ESCALATION_TEAMS = {"dba-team"}
    NOISE_SERVICES = {
        "api-gateway", "auth-service", "user-db",
        "notification-service", "email-queue"
    }  # irrelevant to this scenario
    MAX_STEPS = 15
    SPEED_THRESHOLD = 10

    def score(self, state: EpisodeState) -> float:
        """
        Score the completed Task 3 episode.
        Penalizes both over-escalation (P1) and under-escalation (P3).
        Rewards noise filtering — penalizes actions on irrelevant services.
        """
        total = 0.0
        breakdown = {}

        # ── 1. Severity classification ─────────────────────────────────────────
        severity_value = self._get_first_value(state, "classify_severity")
        if severity_value == self.CORRECT_SEVERITY:
            total += 0.30
            breakdown["severity"] = "+0.30 (correct: P2)"
        elif severity_value == "P1":
            total -= 0.15
            breakdown["severity"] = "-0.15 (over-escalation: P1 given, P2 expected — no outage yet)"
        elif severity_value == "P3":
            total -= 0.15
            breakdown["severity"] = "-0.15 (under-escalation: P3 given, P2 expected — trend is serious)"
        elif severity_value is None:
            breakdown["severity"] = "+0.00 (never classified)"
        else:
            breakdown["severity"] = f"+0.00 (wrong: {severity_value})"

        # ── 2. Root cause identification ───────────────────────────────────────
        root_cause_value = self._get_first_value(state, "identify_root_cause")
        if root_cause_value == self.CORRECT_ROOT_CAUSE:
            total += 0.30
            breakdown["root_cause"] = "+0.30 (correct: payment-db)"
        elif root_cause_value == "payment-service":
            total += 0.10  # close — right payment tier, wrong component
            breakdown["root_cause"] = "+0.10 (partial: payment-service, but root is payment-db)"
        elif root_cause_value in self.NOISE_SERVICES:
            breakdown["root_cause"] = f"+0.00 (wrong: {root_cause_value} is a noise service)"
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
                if (
                    prefix in self.CORRECT_REMEDIATION_PREFIXES
                    and service == self.CORRECT_REMEDIATION_SERVICE
                ):
                    total += 0.20
                    breakdown["remediation"] = f"+0.20 (correct: {value})"
                    remediation_scored = True
                    break
                elif service == self.CORRECT_REMEDIATION_SERVICE:
                    total += 0.05  # right service, suboptimal action
                    breakdown["remediation"] = f"+0.05 (partial: right service, suboptimal action)"
                    remediation_scored = True
                    break

        # Also accept correct escalation to dba-team as valid resolution
        if not remediation_scored:
            escalation_actions = self._get_actions_of_type(state, "escalate")
            for action in escalation_actions:
                if action.get("value") in self.CORRECT_ESCALATION_TEAMS:
                    total += 0.15  # escalation is slightly less credit than direct fix
                    breakdown["remediation"] = "+0.15 (escalated to dba-team — acceptable)"
                    remediation_scored = True
                    break

        if not remediation_scored:
            breakdown["remediation"] = "+0.00 (no correct remediation or escalation)"

        # ── 4. Noise filtering bonus ───────────────────────────────────────────
        # Check if agent took any unnecessary actions on noise services
        spurious_actions = 0
        all_actions = state.action_history
        for action in all_actions:
            action_type = action.get("action_type")
            value = action.get("value", "")
            # Check remediate/escalate/identify actions on noise services
            if action_type == "identify_root_cause" and value in self.NOISE_SERVICES:
                spurious_actions += 1
            elif action_type == "remediate":
                service = value.split(":")[-1] if ":" in value else ""
                if service in self.NOISE_SERVICES:
                    spurious_actions += 1
            elif action_type == "escalate" and value not in self.CORRECT_ESCALATION_TEAMS and value != "sre-team":
                spurious_actions += 1

        if spurious_actions == 0:
            total += 0.10
            breakdown["noise_filtering"] = "+0.10 (no spurious actions on noise services)"
        elif spurious_actions == 1:
            breakdown["noise_filtering"] = f"+0.00 ({spurious_actions} spurious action)"
        else:
            total -= 0.05
            breakdown["noise_filtering"] = f"-0.05 ({spurious_actions} spurious actions — poor noise filtering)"

        # ── 5. Speed bonus ─────────────────────────────────────────────────────
        if self._episode_resolved(state) or remediation_scored:
            if self._steps_used(state) <= self.SPEED_THRESHOLD:
                total += 0.10
                breakdown["speed"] = f"+0.10 (acted within {self._steps_used(state)} steps)"
            else:
                breakdown["speed"] = f"+0.00 (acted but used {self._steps_used(state)} steps)"
        else:
            total -= 0.10
            breakdown["resolution"] = "-0.10 (never acted on the degradation)"

        self._breakdown = breakdown
        return self._clamp(total)

    def get_breakdown(self) -> dict:
        return getattr(self, "_breakdown", {})
