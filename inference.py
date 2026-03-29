"""
inference.py — Baseline Inference Script for LogTriageEnv
==========================================================
MANDATORY environment variables:
    API_BASE_URL   The API endpoint for the LLM
                   (default: https://router.huggingface.co/v1)
    MODEL_NAME     The model identifier to use for inference
    HF_TOKEN       Your Hugging Face / API key

Usage:
    # Set environment variables
    $env:API_BASE_URL="https://api.groq.com/openai/v1"   # or HF router
    $env:MODEL_NAME="llama-3.3-70b-versatile"             # or any model
    $env:HF_TOKEN="your-api-key-here"

    python inference.py

Runtime: < 20 minutes on vcpu=2, memory=8gb
"""
from __future__ import annotations
import os
import json
import time
import requests
from openai import OpenAI

# ─── MANDATORY ENV VARIABLES (as required by hackathon spec) ──────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("GROQ_API_KEY")  # HF_TOKEN is primary

# ─── ENVIRONMENT CONFIG ───────────────────────────────────────────────────────

ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")
TASKS = ["single_crash", "cascading_failure", "silent_degradation"]
MAX_STEPS_PER_TASK = {
    "single_crash": 8,
    "cascading_failure": 12,
    "silent_degradation": 15,
}
SEED = 42  # fixed seed for reproducibility

# ─── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) performing incident triage.
You will receive log lines from a microservice cluster and must diagnose and resolve the incident.

Available services: api-gateway, auth-service, user-db, payment-service, payment-db, notification-service, email-queue
Available teams: sre-team, backend-team, dba-team, security-team

You must respond with ONLY a valid JSON object in this exact format:
{
  "action_type": "<one of: classify_severity, identify_root_cause, escalate, remediate, request_more_logs, resolve, ignore>",
  "value": "<depends on action_type>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>"
}

Value rules by action_type:
- classify_severity: value must be "P1", "P2", or "P3"
- identify_root_cause: value must be a service name from the list above
- escalate: value must be a team name from the list above
- remediate: value must be "restart:<service>", "rollback:<service>", "scale:<service>", "flush-cache:<service>", or "kill-query:<service>"
- request_more_logs: value must be a service name or "all"
- resolve: value must be "resolved"
- ignore: value must be "noise"

Severity classification rules:
- P1: service DOWN or error rate > 5% — immediate customer impact
- P2: degraded performance, trending toward P1 — no outage yet
- P3: warning only, no immediate impact

Strategy:
1. Read all log lines carefully — identify ERROR and FATAL lines first
2. Check system_state for each service (error_rate, latency_p99_ms, status)
3. Find the ROOT CAUSE service (where the problem STARTED, not where it SPREAD)
4. Classify severity based on actual current impact
5. Apply fix to ROOT CAUSE service, not symptom services
6. After classify + identify + remediate — call resolve

IMPORTANT: Respond with ONLY the JSON object. No explanation, no markdown, no backticks."""


def _build_user_prompt(obs: dict) -> str:
    """Convert observation dict into LLM prompt."""
    lines = []

    # System state — only show services with issues
    lines.append("=== SYSTEM STATE ===")
    shown_any = False
    for svc, status in obs.get("system_state", {}).items():
        if isinstance(status, dict):
            s = status.get("status", "unknown")
            er = status.get("error_rate", 0)
            lat = status.get("latency_p99_ms", 0)
            if s != "up" or er > 0.01 or lat > 200:
                lines.append(f"  {svc}: status={s} | error_rate={er:.1%} | latency_p99={lat}ms")
                shown_any = True
    if not shown_any:
        lines.append("  All services appear healthy")
    lines.append("")

    # Active alerts
    alerts = obs.get("active_alerts", [])
    if alerts:
        lines.append("=== ACTIVE ALERTS ===")
        for alert in alerts:
            lines.append(f"  ⚠ {alert}")
        lines.append("")

    # Log lines — show all of them
    lines.append("=== LOG LINES ===")
    for log in obs.get("logs", []):
        if isinstance(log, dict):
            ts = log.get("timestamp", "")[-8:]
            level = log.get("level", "INFO")
            svc = log.get("service", "unknown")
            msg = log.get("message", "")
            lines.append(f"  [{ts}] {level:<5} {svc:<25} {msg}")
    lines.append("")

    # Context
    step = obs.get("step_count", 0)
    task = obs.get("task_id", "")
    elapsed = obs.get("time_elapsed_seconds", 0)
    lines.append(f"Step: {step} | Task: {task} | Time elapsed: {elapsed}s")

    # Feedback from last action
    feedback = obs.get("last_action_feedback", "")
    if feedback and "Incident detected" not in feedback:
        lines.append(f"Last feedback: {feedback}")

    lines.append("")
    lines.append("Respond with JSON only.")
    return "\n".join(lines)


def _parse_action(response_text: str) -> dict | None:
    """Parse LLM response into action dict."""
    text = response_text.strip()

    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        action = json.loads(text)
        if "action_type" not in action or "value" not in action:
            return None
        action.setdefault("confidence", 0.8)
        action.setdefault("reasoning", "")
        return action
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None


def _get_fallback_action(obs: dict, step: int, actions_taken: list) -> dict:
    """Fallback when LLM fails — use simple heuristics."""
    system_state = obs.get("system_state", {})

    # Find worst service
    worst_service = "payment-service"
    worst_error_rate = 0
    for svc, status in system_state.items():
        if isinstance(status, dict):
            er = status.get("error_rate", 0)
            if er > worst_error_rate:
                worst_error_rate = er
                worst_service = svc

    action_types_taken = [a.get("action_type") for a in actions_taken]

    if "classify_severity" not in action_types_taken:
        return {"action_type": "classify_severity", "value": "P1",
                "confidence": 0.5, "reasoning": "fallback"}
    elif "identify_root_cause" not in action_types_taken:
        return {"action_type": "identify_root_cause", "value": worst_service,
                "confidence": 0.5, "reasoning": "fallback"}
    elif "remediate" not in action_types_taken:
        return {"action_type": "remediate", "value": f"restart:{worst_service}",
                "confidence": 0.5, "reasoning": "fallback"}
    else:
        return {"action_type": "resolve", "value": "resolved",
                "confidence": 0.5, "reasoning": "fallback"}


def run_task(client: OpenAI, task_id: str, seed: int = 42) -> dict:
    """Run one complete episode for a task. Returns score + breakdown."""
    print(f"\n  Running task: {task_id}...")

    # Reset
    try:
        resp = requests.post(
            f"{ENV_URL}/reset",
            params={"task": task_id, "seed": seed},
            timeout=30
        )
        resp.raise_for_status()
        obs = resp.json()
    except Exception as e:
        print(f"  ERROR: Reset failed: {e}")
        return {"score": 0.0, "error": str(e), "task_id": task_id}

    max_steps = MAX_STEPS_PER_TASK.get(task_id, 10)
    conversation_history = []
    actions_taken = []
    done = obs.get("done", False)
    steps_taken = 0

    while not done and steps_taken < max_steps:
        user_prompt = _build_user_prompt(obs)
        conversation_history.append({"role": "user", "content": user_prompt})

        # Keep conversation history bounded
        if len(conversation_history) > 8:
            conversation_history = conversation_history[-8:]

        # Call LLM
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                ] + conversation_history,
                max_tokens=200,
                temperature=0,
            )
            response_text = response.choices[0].message.content or ""
            conversation_history.append({"role": "assistant", "content": response_text})
            action = _parse_action(response_text)
            if action is None:
                print(f"    Step {steps_taken}: parse failed, using fallback")
                action = _get_fallback_action(obs, steps_taken, actions_taken)
        except Exception as e:
            print(f"    Step {steps_taken}: LLM error ({e}), using fallback")
            action = _get_fallback_action(obs, steps_taken, actions_taken)

        # Step environment
        try:
            step_resp = requests.post(
                f"{ENV_URL}/step",
                json=action,
                timeout=30
            )
            step_resp.raise_for_status()
            obs = step_resp.json()
            done = obs.get("done", False)
            reward = obs.get("reward", 0.0)
            feedback = obs.get("last_action_feedback", "")
            actions_taken.append(action)
            print(f"    Step {steps_taken}: {action['action_type']}({action['value']}) "
                  f"→ reward={reward:+.2f} | {feedback[:50]}")
        except Exception as e:
            print(f"    Step {steps_taken}: environment error: {e}")
            break

        steps_taken += 1
        time.sleep(0.2)  # avoid rate limits

    # Get grader score
    try:
        grader_resp = requests.post(f"{ENV_URL}/grader", timeout=30)
        grader_resp.raise_for_status()
        grader_result = grader_resp.json()
        score = grader_result.get("score", 0.0)
        breakdown = grader_result.get("breakdown", {})
    except Exception as e:
        print(f"  ERROR: Grader failed: {e}")
        score = obs.get("cumulative_score", 0.0)
        breakdown = {}

    print(f"  Score: {score:.4f} ({steps_taken} steps)")
    return {
        "task_id": task_id,
        "score": score,
        "steps_taken": steps_taken,
        "breakdown": breakdown,
    }


def main():
    """Run baseline agent on all 3 tasks and report scores."""

    # Validate env vars
    if not API_KEY:
        raise ValueError(
            "API key not found. Set HF_TOKEN environment variable:\n"
            "  PowerShell: $env:HF_TOKEN='your-key'\n"
            "  CMD:        set HF_TOKEN=your-key"
        )

    # Build client
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    print("=" * 60)
    print("LogTriageEnv — Baseline Inference Script")
    print("=" * 60)
    print(f"API_BASE_URL: {API_BASE_URL}")
    print(f"MODEL_NAME:   {MODEL_NAME}")
    print(f"ENV_URL:      {ENV_URL}")
    print(f"Seed:         {SEED}")
    print("=" * 60)

    # Verify environment
    try:
        health = requests.get(f"{ENV_URL}/health", timeout=10)
        health.raise_for_status()
        print("Environment: OK")
    except Exception as e:
        raise RuntimeError(
            f"Environment not responding at {ENV_URL}\n"
            f"Start with: python -m uvicorn server.app:app --port 7860\n"
            f"Error: {e}"
        )

    # Run all tasks
    results = []
    start_time = time.time()

    for task_id in TASKS:
        result = run_task(client, task_id, seed=SEED)
        results.append(result)

    elapsed = time.time() - start_time

    # Print report
    print("\n" + "=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)

    total = 0.0
    for result in results:
        task = result["task_id"]
        score = result["score"]
        steps = result["steps_taken"]
        total += score
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"{task:<25} {score:.4f}  [{bar}]  ({steps} steps)")
        for k, v in result.get("breakdown", {}).items():
            print(f"  {k:<20} {v}")

    avg = total / len(TASKS)
    print("-" * 60)
    print(f"{'AVERAGE':<25} {avg:.4f}")
    print(f"{'RUNTIME':<25} {elapsed:.1f}s")
    print("=" * 60)

    # JSON output
    output = {
        "api_base_url": API_BASE_URL,
        "model_name": MODEL_NAME,
        "seed": SEED,
        "results": results,
        "average_score": round(avg, 4),
        "runtime_seconds": round(elapsed, 1),
    }
    print("\nJSON Output:")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    main()
