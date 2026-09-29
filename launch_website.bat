@echo off
title IBVAP - Tactical C4I Web Server
echo =====================================================================
echo  IBVAP: Intelligent Border Vigilance & Analytics Platform
echo  Starting Edge Web Server...
echo =====================================================================

cd /d "%~dp0"

:: Start the Python server in a separate window or directly
echo Launching server at http://localhost:8000 ...
start "" http://localhost:8000
python run_server.py

pause
