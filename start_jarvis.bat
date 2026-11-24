@echo off
title JARVIS // Discrete Local AI Core
echo ========================================================
echo  Starting JARVIS Discrete Assistant (Pure Local Core)
echo ========================================================
echo Host: http://127.0.0.1:8765
echo Sandbox: AST Guarded Python 3 Subprocess
echo.

cd /d "%~dp0"

:: Open default browser to JARVIS UI
start http://127.0.0.1:8765

:: Run the FastAPI Uvicorn Server
python main.py

pause
