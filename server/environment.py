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
from server.scenarios import cascading
from server.scenarios import silent_degrade
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
        elif task_id == "cascading_failure":
            self._ground_truth = cascading.GROUND_TRUTH
        elif task_id == "silent_degradation":
            self._ground_truth = silent_degrade.GROUND_TRUTH

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
        self._state.action_history.append(action.model_dump())
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
        elif self._task_id == "cascading_failure":
            return cascading.get_step_data(step, self._base_time, self._rng)
        elif self._task_id == "silent_degradation":
            return silent_degrade.get_step_data(step, self._base_time, self._rng)
        return [], generate_healthy_system_state(self._base_time)

    def _get_alerts(self, step: int) -> list[str]:
        """Get active alerts for the current step."""
        if self._task_id == "single_crash":
            return single_crash.get_active_alerts(step)
        elif self._task_id == "cascading_failure":
            return cascading.get_active_alerts(step)
        elif self._task_id == "silent_degradation":
            return silent_degrade.get_active_alerts(step)
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
