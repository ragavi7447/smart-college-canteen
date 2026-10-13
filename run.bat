@echo off
title Smart College Canteen (HTTPS)
cd /d "%~dp0"
echo Starting College Canteen (HTTPS)...
timeout /t 2 /nobreak >nul
start "" "https://127.0.0.1:8000/"
python main.py
pause