@echo off
title SQLWhisperer Launcher
color 0A

echo.
echo  ========================================
echo    SQLWhisperer - Starting Services
echo  ========================================
echo.

:: Check for .env file (auto-create if missing)
if not exist ".env" (
    echo [!] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [i] Tip: You can set OPENAI_API_KEY in .env or enter it directly in the Streamlit UI!
)

:: Check for Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [X] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Create data and log directories
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "data\user_uploads" mkdir data\user_uploads

:: Ensure SQLite demo dataset exists
if not exist "data\demo_ecommerce.db" (
    echo [*] Initializing embedded SQLite demo dataset...
    python -m scripts.seed_sqlite >nul 2>&1
)

:: Install dependencies if needed
echo [1/5] Checking dependencies...
pip show langchain >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo       Installing dependencies...
    pip install -r requirements.txt
)

:: Seed few-shot examples (idempotent - skips if already seeded)
echo [2/5] Checking few-shot vector store...
python -m scripts.seed_few_shots 2>nul

:: Start Local SLM GPU server if model exists and port 8001 not listening
netstat -aon | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    if exist "models\sqlwhisperer-slm-lora" (
        echo [*] Starting Local SLM Server (RTX 4050) on http://localhost:8001 ...
        start /B "SQLWhisperer-SLM" cmd /c "python scripts\serve_local_slm.py > logs\slm.log 2>&1"
        timeout /t 2 /nobreak >nul
    )
)

:: Start FastAPI backend
echo [3/5] Starting FastAPI backend on http://localhost:8000 ...
start /B "SQLWhisperer-API" cmd /c "python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload > logs\api.log 2>&1"

:: Wait for API to be ready
echo [4/5] Waiting for API to start...
timeout /t 4 /nobreak >nul

:: Start Streamlit frontend
echo [5/5] Starting Streamlit frontend on http://localhost:8501 ...
start /B "SQLWhisperer-UI" cmd /c "python -m streamlit run streamlit_app/app.py --server.port 8501 --server.headless true > logs\streamlit.log 2>&1"

timeout /t 3 /nobreak >nul

echo.
echo  ========================================
echo    SQLWhisperer is running!
echo  ========================================
echo.
echo    Local SLM (GPU): http://localhost:8001 (RTX 4050)
echo    Streamlit UI:    http://localhost:8501
echo    API Docs:        http://localhost:8000/docs
echo    API Log:         logs\api.log
echo    UI Log:          logs\streamlit.log
echo.
echo    Run stop.bat to shut down all services.
echo  ========================================
echo.

:: Open browser
start http://localhost:8501

pause
