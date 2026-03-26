@echo off
REM =========================================================================
REM Day 1 Test & Verification Script for LogTriageEnv
REM =========================================================================
REM This script runs all Day 1 tests and verifies the project is ready

echo =========================================================================
echo LogTriageEnv — Day 1 Verification Script
echo =========================================================================

REM Test 1: Python Tests
echo.
echo [TEST 1] Running Python validation tests...
python test_day1.py
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Python tests failed!
    exit /b 1
)

REM Test 2: Install dependencies
echo.
echo [TEST 2] Installing dependencies from requirements.txt...
pip install -q -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Pip install failed!
    exit /b 1
)
echo ✅ Dependencies installed

REM Test 3: Check FastAPI can import
echo.
echo [TEST 3] Checking FastAPI imports...
python -c "from fastapi import FastAPI; from uvicorn import run; print('✅ FastAPI and Uvicorn OK')"
if %ERRORLEVEL% NEQ 0 (
    echo ❌ FastAPI/Uvicorn import failed!
    exit /b 1
)

REM Test 4: Check Pydantic models
echo.
echo [TEST 4] Testing Pydantic models...
python -c "from server.models import TriageAction, TriageObservation; print('✅ Models imported')"
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Models import failed!
    exit /b 1
)

echo.
echo =========================================================================
echo ✅ ALL TESTS PASSED!
echo =========================================================================
echo.
echo Next steps:
echo.
echo 1. START THE SERVER:
echo    python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
echo.
echo 2. TEST ENDPOINTS (open another terminal):
echo    curl http://localhost:7860/health
echo    curl http://localhost:7860/tasks
echo.
echo 3. TEST DOCKER BUILD:
echo    docker build -t logtriage-env .
echo    docker run -p 7860:7860 logtriage-env
echo.
echo 4. PUSH TO GITHUB:
echo    git add .
echo    git commit -m "Day 1: scaffold, models.py, app skeleton, Dockerfile"
echo    git push origin main
echo.
pause
