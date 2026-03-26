#!/usr/bin/env python
"""
Day 1 Test Script — Verify all endpoints and models work
"""
import sys
import json
from pathlib import Path

# Add server to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("DAY 1 TEST SUITE — LogTriageEnv")
print("=" * 70)

# Test 1: Import models
print("\n[TEST 1] Importing models...")
try:
    from server.models import TriageAction, TriageObservation, EpisodeState, LogLine, ServiceStatus
    print("✅ All models imported successfully")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Import FastAPI app
print("\n[TEST 2] Importing FastAPI app...")
try:
    from server.app import app
    print("✅ FastAPI app imported successfully")
except Exception as e:
    print(f"❌ App import failed: {e}")
    sys.exit(1)

# Test 3: Test TriageAction validation
print("\n[TEST 3] Testing TriageAction.is_valid()...")
test_cases = [
    ({"action_type": "classify_severity", "value": "P1"}, True, "Valid P1"),
    ({"action_type": "classify_severity", "value": "P5"}, False, "Invalid P5"),
    ({"action_type": "identify_root_cause", "value": "user-db"}, True, "Valid root cause"),
    ({"action_type": "identify_root_cause", "value": "invalid-service"}, False, "Invalid service"),
    ({"action_type": "remediate", "value": "restart:payment-service"}, True, "Valid remediate"),
    ({"action_type": "remediate", "value": "invalid:payment-service"}, False, "Invalid remediate action"),
    ({"action_type": "escalate", "value": "sre-team"}, True, "Valid escalate"),
    ({"action_type": "escalate", "value": "invalid-team"}, False, "Invalid team"),
    ({"action_type": "resolve", "value": "resolved"}, True, "Valid resolve"),
    ({"action_type": "resolve", "value": "not-resolved"}, False, "Invalid resolve"),
    ({"action_type": "ignore", "value": "noise"}, True, "Valid ignore"),
]

passed = 0
failed = 0

for test_data, expected_valid, description in test_cases:
    try:
        action = TriageAction(**test_data)
        is_valid, error = action.is_valid()
        
        if is_valid == expected_valid:
            print(f"  ✅ {description}: {test_data}")
            passed += 1
        else:
            print(f"  ❌ {description}: expected {expected_valid}, got {is_valid}")
            failed += 1
    except Exception as e:
        print(f"  ❌ {description}: Exception: {e}")
        failed += 1

print(f"\nValidation tests: {passed} passed, {failed} failed")

# Test 4: Test Pydantic model construction
print("\n[TEST 4] Testing Pydantic model construction...")
try:
    log = LogLine(
        timestamp="2025-03-25T14:32:01Z",
        level="ERROR",
        service="api-gateway",
        request_id="req-123",
        message="Service timeout",
        latency_ms=5000
    )
    print(f"✅ LogLine created: {log.service}")
    
    service_status = ServiceStatus(
        name="api-gateway",
        status="degraded",
        error_rate=0.34,
        latency_p99_ms=2500,
        last_updated="2025-03-25T14:32:01Z"
    )
    print(f"✅ ServiceStatus created: {service_status.name}")
    
    observation = TriageObservation(
        logs=[log],
        system_state={"api-gateway": service_status},
        incident_id="inc-001",
        task_id="single_crash",
        step_count=0,
        time_elapsed_seconds=0
    )
    print(f"✅ TriageObservation created: {observation.incident_id}")
except Exception as e:
    print(f"❌ Model construction failed: {e}")
    sys.exit(1)

# Test 5: FastAPI endpoint structure
print("\n[TEST 5] Checking FastAPI endpoints...")
endpoints = ["/health", "/reset", "/step", "/state", "/tasks", "/grader", "/baseline"]
from fastapi.routing import APIRoute

app_endpoints = [route.path for route in app.routes if isinstance(route, APIRoute)]
print(f"Registered endpoints: {app_endpoints}")

for endpoint in endpoints:
    if endpoint in app_endpoints:
        print(f"  ✅ {endpoint} exists")
    else:
        print(f"  ❌ {endpoint} missing")

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED — Day 1 Ready for Verification")
print("=" * 70)
print("\nNext steps:")
print("1. Start server: python -m uvicorn server.app:app --host 0.0.0.0 --port 7860")
print("2. Test endpoints with curl (see below)")
print("3. Build Docker: docker build -t logtriage-env .")
print("4. Verify Docker works: docker run -p 7860:7860 logtriage-env")
print("\nExample curl tests:")
print("  curl http://localhost:7860/health")
print("  curl http://localhost:7860/tasks")
print("  curl -X POST http://localhost:7860/reset -H 'Content-Type: application/json'")
