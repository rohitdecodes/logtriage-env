"""
Manual grader testing CLI.
Run a simulated episode and score it with the official grader.

Usage:
    python scripts/run_grader.py --task single_crash --agent correct
    python scripts/run_grader.py --task cascading_failure --agent wrong
    python scripts/run_grader.py --task silent_degradation --agent correct
    python scripts/run_grader.py --all
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.environment import LogTriageEnvironment
from server.models import TriageAction
from server.graders import score_episode

# ─── CORRECT AGENT SCRIPTS ────────────────────────────────────────────────────

CORRECT_ACTIONS = {
    "single_crash": [
        TriageAction(action_type="classify_severity",   value="P1",                       confidence=0.95),
        TriageAction(action_type="identify_root_cause", value="payment-service",           confidence=0.90),
        TriageAction(action_type="remediate",           value="restart:payment-service",   confidence=0.85),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
    "cascading_failure": [
        TriageAction(action_type="classify_severity",   value="P1",                       confidence=0.90),
        TriageAction(action_type="identify_root_cause", value="user-db",                  confidence=0.85),
        TriageAction(action_type="remediate",           value="kill-query:user-db",        confidence=0.90),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
    "silent_degradation": [
        TriageAction(action_type="request_more_logs",   value="payment-db",               confidence=0.70),
        TriageAction(action_type="classify_severity",   value="P2",                       confidence=0.80),
        TriageAction(action_type="identify_root_cause", value="payment-db",               confidence=0.85),
        TriageAction(action_type="remediate",           value="flush-cache:payment-db",    confidence=0.80),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
}

# ─── WRONG AGENT SCRIPTS ──────────────────────────────────────────────────────

WRONG_ACTIONS = {
    "single_crash": [
        TriageAction(action_type="classify_severity",   value="P3",                       confidence=0.50),
        TriageAction(action_type="identify_root_cause", value="api-gateway",              confidence=0.50),
        TriageAction(action_type="remediate",           value="restart:api-gateway",       confidence=0.50),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
    "cascading_failure": [
        TriageAction(action_type="classify_severity",   value="P2",                       confidence=0.60),
        TriageAction(action_type="identify_root_cause", value="api-gateway",              confidence=0.60),
        TriageAction(action_type="remediate",           value="restart:api-gateway",       confidence=0.60),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
    "silent_degradation": [
        TriageAction(action_type="classify_severity",   value="P1",                       confidence=0.90),
        TriageAction(action_type="identify_root_cause", value="api-gateway",              confidence=0.70),
        TriageAction(action_type="remediate",           value="restart:api-gateway",       confidence=0.70),
        TriageAction(action_type="resolve",             value="resolved",                  confidence=1.00),
    ],
}


def run_test(task_id: str, agent_type: str, seed: int = 42) -> dict:
    """Run a full episode with given actions and return grader result."""
    env = LogTriageEnvironment()
    env.reset(task_id=task_id, seed=seed)

    actions = CORRECT_ACTIONS[task_id] if agent_type == "correct" else WRONG_ACTIONS[task_id]

    for action in actions:
        obs = env.step(action)
        if obs.done:
            break

    result = score_episode(task_id, env.state)
    return result


def print_result(task_id: str, agent_type: str, result: dict):
    score = result["score"]
    print(f"\n{'='*60}")
    print(f"Task:     {task_id}")
    print(f"Agent:    {agent_type}")
    print(f"Score:    {score:.4f}")
    print(f"Steps:    {result['steps_taken']}/{result['max_steps']}")
    print(f"Resolved: {result['resolved']}")
    print(f"\nBreakdown:")
    for key, val in result.get("breakdown", {}).items():
        print(f"  {key:<20} {val}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Test LogTriageEnv graders")
    parser.add_argument("--task", choices=["single_crash", "cascading_failure", "silent_degradation"],
                        help="Task to test")
    parser.add_argument("--agent", choices=["correct", "wrong"], default="correct",
                        help="Agent type to simulate")
    parser.add_argument("--all", action="store_true",
                        help="Run all tasks with both correct and wrong agents")
    args = parser.parse_args()

    if args.all:
        tasks = ["single_crash", "cascading_failure", "silent_degradation"]
        print("\n[TEST] Running all tasks with correct and wrong agents...\n")
        print(f"{'Task':<25} {'Agent':<10} {'Score':<8} {'Variance'}")
        print("-" * 60)
        for task in tasks:
            correct_result = run_test(task, "correct")
            wrong_result = run_test(task, "wrong")
            correct_score = correct_result["score"]
            wrong_score = wrong_result["score"]
            variance = correct_score - wrong_score
            status = "[OK]" if variance > 0.10 else "[LOW]"
            print(f"{task:<25} correct    {correct_score:.4f}")
            print(f"{task:<25} wrong      {wrong_score:.4f}   delta={variance:.4f} {status}")
            print()
    elif args.task:
        result = run_test(args.task, args.agent)
        print_result(args.task, args.agent, result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
