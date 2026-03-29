"""
Baseline inference script for LogTriageEnv.
Uses an LLM agent to play all 3 tasks and produce reproducible scores.

Usage:
    # Set API key as environment variable (never hardcode)
    export GROQ_API_KEY=your_key_here       # Linux/Mac
    set GROQ_API_KEY=your_key_here          # Windows CMD
    $env:GROQ_API_KEY="your_key_here"       # Windows PowerShell

    python baseline.py

Environment variables:
    GROQ_API_KEY      - Groq API key (primary)
    NVIDIA_API_KEY    - NVIDIA NIM API key (fallback)
    OPENROUTER_API_KEY - OpenRouter API key (fallback)
    OPENAI_API_KEY    - OpenAI API key (fallback)
    ENV_URL           - Base URL of deployed environment (default: http://localhost:7860)
"""
from __future__ import annotations
import os
import json
import time
import requests
from openai import OpenAI

# ─── PROVIDER CONFIG — change PROVIDER to switch. Nothing else changes. ───────

PROVIDER = "groq"  # options: "groq", "nvidia", "openrouter", "openai"

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "openai/gpt-oss-20b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.1-8b-instruct:free",
    },
    "openai": {
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
}

# ─── ENVIRONMENT CONFIG ───────────────────────────────────────────────────────

ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")
TASKS = ["single_crash", "cascading_failure", "silent_degradation"]
MAX_STEPS_PER_TASK = {"single_crash": 8, "cascading_failure": 12, "silent_degradation": 15}
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

Strategy:
1. Read all log lines carefully
2. Look at system_state for service health (error_rate, latency_p99_ms, status)
3. Identify which service is the ROOT CAUSE (not just a symptom)
4. Classify severity based on actual impact:
   - P1: service down or error rate > 5% (customer impact)
   - P2: degraded performance, trending toward P1 (no outage yet)
   - P3: warning, no immediate impact
5. Apply the correct fix to the ROOT CAUSE service, not symptom services
6. Once you have classified, identified root cause, and remediated — resolve the incident

IMPORTANT: Respond with ONLY the JSON object. No explanation, no markdown, no backticks."""


def _build_user_prompt(obs: dict) -> str:
    """Convert observation dict to a prompt string for the LLM."""
    lines = []

    # System state summary
    lines.append("=== SYSTEM STATE ===")
    for svc, status in obs.get("system_state", {}).items():
        if isinstance(status, dict):
            s = status.get("status", "unknown")
            er = status.get("error_rate", 0)
            lat = status.get("latency_p99_ms", 0)
            if s != "up" or er > 0.01 or lat > 200:
                lines.append(f"  {svc}: {s} | error_rate={er:.1%} | latency_p99={lat}ms")
    lines.append("")

    # Active alerts
    alerts = obs.get("active_alerts", [])
    if alerts:
        lines.append("=== ACTIVE ALERTS ===")
        for alert in alerts:
            lines.append(f"  {alert}")
        lines.append("")

    # Log lines
    lines.append("=== LOG LINES ===")
    for log in obs.get("logs", []):
        if isinstance(log, dict):
            ts = log.get("timestamp", "")[-8:]  # just time part
            level = log.get("level", "INFO")
            svc = log.get("service", "unknown")
            msg = log.get("message", "")
            lines.append(f"  [{ts}] {level:<5} {svc:<25} {msg}")
    lines.append("")

    # Episode context
    lines.append(f"Step: {obs.get('step_count', 0)} | "
                 f"Task: {obs.get('task_id', '')} | "
                 f"Time elapsed: {obs.get('time_elapsed_seconds', 0)}s")

    # Feedback from last action
    feedback = obs.get("last_action_feedback", "")
    if feedback and feedback != "Incident detected. Analyze the logs and take action.":
        lines.append(f"Last action feedback: {feedback}")

    lines.append("")
    lines.append("Based on the above, what is your next triage action? Respond with JSON only.")
    return "\n".join(lines)


def _parse_action(response_text: str) -> dict | None:
    """Parse LLM response into action dict. Returns None if parsing fails."""
    text = response_text.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        action = json.loads(text)
        # Validate required fields
        if "action_type" not in action or "value" not in action:
            return None
        # Ensure confidence and reasoning exist
        action.setdefault("confidence", 0.8)
        action.setdefault("reasoning", "")
        return action
    except json.JSONDecodeError:
        # Try to extract JSON from text
        import re
        match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None


def _get_fallback_action(obs: dict, step: int) -> dict:
    """
    Fallback action when LLM fails to produce valid JSON.
    Uses simple heuristics to make a reasonable action.
    """
    system_state = obs.get("system_state", {})
    task_id = obs.get("task_id", "")

    # Find the most degraded service
    worst_service = None
    worst_error_rate = 0
    for svc, status in system_state.items():
        if isinstance(status, dict):
            er = status.get("error_rate", 0)
            if er > worst_error_rate:
                worst_error_rate = er
                worst_service = svc

    if step == 0:
        return {"action_type": "classify_severity", "value": "P1", "confidence": 0.5, "reasoning": "fallback"}
    elif step == 1 and worst_service:
        return {"action_type": "identify_root_cause", "value": worst_service, "confidence": 0.5, "reasoning": "fallback"}
    elif step == 2 and worst_service:
        return {"action_type": "remediate", "value": f"restart:{worst_service}", "confidence": 0.5, "reasoning": "fallback"}
    else:
        return {"action_type": "resolve", "value": "resolved", "confidence": 0.5, "reasoning": "fallback"}


def run_task(client: OpenAI, model: str, task_id: str, seed: int = 42) -> dict:
    """
    Run one complete episode for a given task.
    Returns dict with score, steps, and breakdown.
    """
    print(f"\n  Running task: {task_id}...")

    # Reset environment
    try:
        resp = requests.post(
            f"{ENV_URL}/reset",
            params={"task": task_id, "seed": seed},
            timeout=30
        )
        resp.raise_for_status()
        obs = resp.json()
    except Exception as e:
        print(f"  ERROR: Failed to reset environment: {e}")
        return {"score": 0.0, "error": str(e), "task_id": task_id}

    max_steps = MAX_STEPS_PER_TASK.get(task_id, 10)
    conversation_history = []
    steps_taken = 0
    done = obs.get("done", False)

    while not done and steps_taken < max_steps:
        # Build prompt from observation
        user_prompt = _build_user_prompt(obs)

        # Add to conversation history (keep last 4 exchanges for context)
        conversation_history.append({"role": "user", "content": user_prompt})
        if len(conversation_history) > 8:
            conversation_history = conversation_history[-8:]

        # Call LLM
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                ] + conversation_history,
                max_tokens=200,
                temperature=0,  # deterministic
            )
            response_text = response.choices[0].message.content
            conversation_history.append({"role": "assistant", "content": response_text})

            # Parse action
            action = _parse_action(response_text)
            if action is None:
                print(f"    Step {steps_taken}: LLM parse failed, using fallback")
                action = _get_fallback_action(obs, steps_taken)

        except Exception as e:
            print(f"    Step {steps_taken}: LLM call failed ({e}), using fallback")
            action = _get_fallback_action(obs, steps_taken)

        # Take action in environment
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

            print(f"    Step {steps_taken}: {action['action_type']}({action['value']}) "
                  f"-> reward={reward:+.2f} | {feedback[:60]}")

        except Exception as e:
            print(f"    Step {steps_taken}: Environment step failed: {e}")
            break

        steps_taken += 1
        time.sleep(0.1)  # small delay to avoid rate limits

    # Get official grader score
    try:
        grader_resp = requests.post(f"{ENV_URL}/grader", timeout=30)
        grader_resp.raise_for_status()
        grader_result = grader_resp.json()
        score = grader_result.get("score", 0.0)
        breakdown = grader_result.get("breakdown", {})
    except Exception as e:
        print(f"  ERROR: Grader call failed: {e}")
        score = obs.get("cumulative_score", 0.0)
        breakdown = {}

    print(f"  Final score: {score:.4f} ({steps_taken} steps)")
    return {
        "task_id": task_id,
        "score": score,
        "steps_taken": steps_taken,
        "breakdown": breakdown,
    }


def main():
    """Run baseline agent against all 3 tasks and report scores."""

    # ── Setup provider ─────────────────────────────────────────────────────────
    provider_config = PROVIDERS[PROVIDER]
    api_key = os.environ.get(provider_config["api_key_env"])
    model = provider_config["model"]
    base_url = provider_config["base_url"]

    if not api_key:
        raise ValueError(
            f"API key not found. Set environment variable: {provider_config['api_key_env']}\n"
            f"  Windows PowerShell: $env:{provider_config['api_key_env']}='your_key'\n"
            f"  Windows CMD:        set {provider_config['api_key_env']}=your_key"
        )

    # Build OpenAI-compatible client
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    print("=" * 60)
    print("LogTriageEnv — Baseline Inference Script")
    print("=" * 60)
    print(f"Provider:    {PROVIDER}")
    print(f"Model:       {model}")
    print(f"Environment: {ENV_URL}")
    print(f"Seed:        {SEED}")
    print(f"Tasks:       {', '.join(TASKS)}")
    print("=" * 60)

    # ── Verify environment is running ──────────────────────────────────────────
    try:
        health = requests.get(f"{ENV_URL}/health", timeout=10)
        health.raise_for_status()
        print(f"Environment health: OK")
    except Exception as e:
        raise RuntimeError(
            f"Environment not responding at {ENV_URL}\n"
            f"Start it with: python -m uvicorn server.app:app --port 7860\n"
            f"Error: {e}"
        )

    # ── Run all tasks ──────────────────────────────────────────────────────────
    results = []
    for task_id in TASKS:
        result = run_task(client, model, task_id, seed=SEED)
        results.append(result)

    # ── Print final report ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)

    total_score = 0.0
    for result in results:
        task = result["task_id"]
        score = result["score"]
        steps = result["steps_taken"]
        total_score += score
        bar = "#" * int(score * 20) + "-" * (20 - int(score * 20))
        print(f"{task:<25} {score:.4f}  [{bar}]  ({steps} steps)")
        if result.get("breakdown"):
            for k, v in result["breakdown"].items():
                print(f"  {k:<20} {v}")

    avg_score = total_score / len(TASKS)
    print("-" * 60)
    print(f"{'AVERAGE':<25} {avg_score:.4f}")
    print("=" * 60)

    # ── Machine-readable output ────────────────────────────────────────────────
    output = {
        "provider": PROVIDER,
        "model": model,
        "seed": SEED,
        "results": results,
        "average_score": round(avg_score, 4),
    }
    print("\nJSON Output (for /baseline endpoint):")
    print(json.dumps(output, indent=2))

    return output


if __name__ == "__main__":
    main()
