from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from server.models import TriageAction, TriageObservation, EpisodeState

app = FastAPI(
    title="LogTriageEnv",
    description="OpenEnv environment for SRE incident triage",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "environment": "logtriage-env", "version": "1.0.0"}


@app.post("/reset")
def reset(task: str = "single_crash", seed: int = None):
    # TODO Day 2: wire to LogTriageEnvironment
    return {"message": "reset endpoint placeholder", "task": task}


@app.post("/step")
def step(action: TriageAction):
    # TODO Day 2: wire to LogTriageEnvironment
    valid, err = action.is_valid()
    if not valid:
        return JSONResponse(status_code=422, content={"error": err})
    return {"message": "step endpoint placeholder", "action_received": action.model_dump()}


@app.get("/state")
def state():
    # TODO Day 2: wire to LogTriageEnvironment
    return {"message": "state endpoint placeholder"}


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
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "cascading_failure",
                "name": "Cascading Failure",
                "difficulty": "medium",
                "max_steps": 12,
                "description": "DB slowdown cascades upstream. Find the true root cause.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
            {
                "id": "silent_degradation",
                "name": "Silent Degradation with Noise",
                "difficulty": "hard",
                "max_steps": 15,
                "description": "Slow degradation hidden in 60% noise. Nuanced P2 judgment.",
                "action_schema": {
                    "action_type": "classify_severity | identify_root_cause | escalate | remediate | request_more_logs | resolve | ignore",
                    "value": "string (depends on action_type)",
                    "confidence": "float [0.0, 1.0]",
                    "reasoning": "string (optional)",
                },
            },
        ]
    }


@app.post("/grader")
def grader():
    # TODO Day 4: wire to grader logic
    return {"message": "grader endpoint placeholder", "score": 0.0}


@app.post("/baseline")
def baseline():
    # TODO Day 5: wire to baseline.py
    return {"message": "baseline endpoint placeholder"}


if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=True)
