@echo off
title SQLWhisperer - Stopping Services
color 0C

echo.
echo  ========================================
echo    SQLWhisperer - Stopping Services
echo  ========================================
echo.

:: Kill Uvicorn (FastAPI)
echo [1/2] Stopping FastAPI backend...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill Streamlit
echo [2/3] Stopping Streamlit frontend...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill Local SLM server (port 8001)
echo [3/3] Stopping Local SLM server...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo  All services stopped.
echo  ========================================
echo.

timeout /t 2 /nobreak >nul
