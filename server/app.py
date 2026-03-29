from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn
import os

from server.models import TriageAction
from server.environment import LogTriageEnvironment

app = FastAPI(
    title="LogTriageEnv",
    description="OpenEnv environment for SRE incident triage",
    version="1.0.0",
)

# One environment instance per server process
env = LogTriageEnvironment()


@app.get("/health")
def health():
    return {"status": "ok", "environment": "logtriage-env", "version": "1.0.0"}


@app.post("/reset")
def reset(
    task: str = Query(default="single_crash", description="Task ID to run"),
    seed: int = Query(default=None, description="Random seed for reproducibility"),
):
    try:
        obs = env.reset(task_id=task, seed=seed)
        return obs.model_dump()
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/step")
def step(action: TriageAction):
    valid, err = action.is_valid()
    if not valid:
        return JSONResponse(status_code=422, content={"error": err})
    try:
        obs = env.step(action)
        return obs.model_dump()
    except RuntimeError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/state")
def state():
    try:
        return env.state.model_dump()
    except RuntimeError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/tasks")
def get_tasks():
    return {
        "tasks": [
            {
                "id": "single_crash",
                "name": "Single Service Crash",
                "difficulty": "easy",
                "max_steps": 8,
                "description": "One service crashes. Classify severity, find root cause, remediate.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "cascading_failure",
                "name": "Cascading Failure",
                "difficulty": "medium",
                "max_steps": 12,
                "description": "DB slowdown cascades upstream. Find the true root cause, not symptoms.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "silent_degradation",
                "name": "Silent Degradation with Noise",
                "difficulty": "hard",
                "max_steps": 15,
                "description": "Slow degradation hidden in 60% noise. Nuanced P2 severity judgment.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type — see README)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
        ]
    }


@app.post("/grader")
def grader():
    try:
        from server.graders import score_episode
        state = env.state
        result = score_episode(state.task_id, state)
        return result
    except RuntimeError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/baseline")
def baseline():
    """
    Run the baseline inference script against all 3 tasks.
    Returns scores for each task produced by the LLM agent.
    Note: Requires GROQ_API_KEY (or other provider key) to be set.
    """
    import subprocess
    import sys
    import json as json_lib

    try:
        # Pass through all current env vars, plus GROQ_API_KEY if set
        env = os.environ.copy()
        groq_key = os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            # Try to read from process that started the server
            pass

        result = subprocess.run(
            [sys.executable, "baseline.py"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
        )

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Baseline script failed",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                }
            )

        # Extract JSON from output
        output_lines = result.stdout.strip().split("\n")
        json_start = None
        for i, line in enumerate(output_lines):
            if line.strip() == "JSON Output (for /baseline endpoint):":
                json_start = i + 1
                break

        if json_start and json_start < len(output_lines):
            json_str = "\n".join(output_lines[json_start:])
            return json_lib.loads(json_str)
        else:
            return {"message": "Baseline completed", "output": result.stdout[-1000:]}

    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=504, content={"error": "Baseline timed out after 5 minutes"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=True)
