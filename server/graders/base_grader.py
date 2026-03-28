"""
Abstract base grader interface.
All task graders must inherit from this and implement score().
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from server.models import EpisodeState


class BaseGrader(ABC):
    """
    Abstract grader base class.

    A grader evaluates the complete episode history and produces
    a final score in [0.0, 1.0].

    Unlike the reward function (which fires after every step),
    the grader fires once at episode end and produces the
    official score used by judges.
    """

    @abstractmethod
    def score(self, state: EpisodeState) -> float:
        """
        Score the completed episode.

        Args:
            state: Final EpisodeState including full action_history

        Returns:
            float in [0.0, 1.0] — the official episode score
        """
        raise NotImplementedError

    def _clamp(self, value: float) -> float:
        """Clamp score to valid range [0.0, 1.0]."""
        return round(max(0.0, min(1.0, value)), 4)

    def _get_actions_of_type(
        self, state: EpisodeState, action_type: str
    ) -> list[dict]:
        """Return all actions of a given type from episode history."""
        return [
            a for a in state.action_history
            if a.get("action_type") == action_type
        ]

    def _was_action_taken(self, state: EpisodeState, action_type: str) -> bool:
        """Check if an action type was taken at any point in the episode."""
        return any(
            a.get("action_type") == action_type
            for a in state.action_history
        )

    def _get_first_value(
        self, state: EpisodeState, action_type: str
    ) -> str | None:
        """Get the value of the first action of a given type."""
        actions = self._get_actions_of_type(state, action_type)
        return actions[0].get("value") if actions else None

    def _episode_resolved(self, state: EpisodeState) -> bool:
        """Check if agent explicitly resolved the episode."""
        return self._was_action_taken(state, "resolve")

    def _steps_used(self, state: EpisodeState) -> int:
        """Return number of steps taken."""
        return state.step_count
