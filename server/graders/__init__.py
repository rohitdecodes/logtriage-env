"""
Grader registry for LogTriageEnv.
Maps task_id strings to grader class instances.
"""
from server.graders.crash_grader import CrashGrader
from server.graders.cascade_grader import CascadeGrader
from server.graders.noise_grader import NoiseGrader

# Registry: task_id → grader instance
GRADER_REGISTRY = {
    "single_crash":       CrashGrader(),
    "cascading_failure":  CascadeGrader(),
    "silent_degradation": NoiseGrader(),
}


def get_grader(task_id: str):
    """
    Get the grader for a given task.
    Raises ValueError if task_id is unknown.
    """
    if task_id not in GRADER_REGISTRY:
        raise ValueError(
            f"No grader registered for task '{task_id}'. "
            f"Valid tasks: {list(GRADER_REGISTRY.keys())}"
        )
    return GRADER_REGISTRY[task_id]


def score_episode(task_id: str, state) -> dict:
    """
    Score a completed episode and return full result dict.
    This is what the /grader endpoint calls.
    """
    grader = get_grader(task_id)
    score = grader.score(state)
    breakdown = grader.get_breakdown() if hasattr(grader, "get_breakdown") else {}

    return {
        "score": score,
        "task_id": task_id,
        "episode_id": state.episode_id,
        "steps_taken": state.step_count,
        "max_steps": state.max_steps,
        "breakdown": breakdown,
        "resolved": any(
            a.get("action_type") == "resolve"
            for a in state.action_history
        ),
    }
