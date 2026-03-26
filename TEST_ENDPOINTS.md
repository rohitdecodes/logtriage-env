# Day 1 Testing Guide — Curl Commands

## Prerequisites
```bash
pip install -r requirements.txt
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

Leave the server running and open a new terminal for these tests.

---

## Test 1: Health Check
```bash
curl http://localhost:7860/health
```

**Expected Response:**
```json
{
  "status": "ok",
  "environment": "logtriage-env",
  "version": "1.0.0"
}
```

---

## Test 2: Get All Tasks
```bash
curl http://localhost:7860/tasks
```

**Expected Response:** JSON with 3 tasks (single_crash, cascading_failure, silent_degradation) including action schemas.

---

## Test 3: Valid Step Action (Classify Severity)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "classify_severity",
    "value": "P1",
    "confidence": 0.95,
    "reasoning": "High error rate detected"
  }'
```

**Expected Response:** 200 OK
```json
{
  "message": "step endpoint placeholder",
  "action_received": {
    "action_type": "classify_severity",
    "value": "P1",
    "confidence": 0.95,
    "reasoning": "High error rate detected"
  }
}
```

---

## Test 4: Valid Step Action (Root Cause)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "identify_root_cause",
    "value": "user-db",
    "confidence": 0.8
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 5: Valid Step Action (Remediate)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "remediate",
    "value": "restart:payment-service",
    "confidence": 0.9
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 6: Valid Step Action (Escalate)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "escalate",
    "value": "dba-team",
    "confidence": 0.85
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 7: Valid Step Action (Resolve)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "resolve",
    "value": "resolved"
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 8: Valid Step Action (Ignore Noise)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "ignore",
    "value": "noise"
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 9: Valid Step Action (Request More Logs)
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "request_more_logs",
    "value": "all",
    "confidence": 0.5
  }'
```

**Expected Response:** 200 OK with action received

---

## Test 10: INVALID Action - Wrong Severity
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "classify_severity",
    "value": "P5"
  }'
```

**Expected Response:** 422 Unprocessable Entity
```json
{
  "error": "classify_severity value must be one of {'P1', 'P2', 'P3'}"
}
```

---

## Test 11: INVALID Action - Unknown Service
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "identify_root_cause",
    "value": "unknown-service"
  }'
```

**Expected Response:** 422 Unprocessable Entity
```json
{
  "error": "identify_root_cause value must be one of {...}"
}
```

---

## Test 12: INVALID Action - Bad Remediate Format
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "remediate",
    "value": "invalid:payment-service"
  }'
```

**Expected Response:** 422 Unprocessable Entity
```json
{
  "error": "remediate prefix must be one of {...}"
}
```

---

## Test 13: INVALID Action - Bad Escalate Team
```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "escalate",
    "value": "marketing-team"
  }'
```

**Expected Response:** 422 Unprocessable Entity
```json
{
  "error": "escalate value must be one of {...}"
}
```

---

## Test 14: Reset Endpoint
```bash
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{
    "task": "single_crash"
  }'
```

**Expected Response:** 200 OK
```json
{
  "message": "reset endpoint placeholder",
  "task": "single_crash"
}
```

---

## Test 15: State Endpoint
```bash
curl http://localhost:7860/state
```

**Expected Response:** 200 OK
```json
{
  "message": "state endpoint placeholder"
}
```

---

## Test 16: Grader Endpoint
```bash
curl -X POST http://localhost:7860/grader
```

**Expected Response:** 200 OK
```json
{
  "message": "grader endpoint placeholder",
  "score": 0.0
}
```

---

## Test 17: Baseline Endpoint
```bash
curl -X POST http://localhost:7860/baseline
```

**Expected Response:** 200 OK
```json
{
  "message": "baseline endpoint placeholder"
}
```

---

## Summary

**Tests 1-9, 14-17:** Should all return 200 OK ✅  
**Tests 10-13:** Should all return 422 with error message ✅

If all pass, your Day 1 is complete! Push to GitHub:

```bash
git add .
git commit -m "Day 1 complete: models, endpoints, Docker, tests, README"
git push origin main
```
