@echo off
title J.A.R.V.I.S. Desktop System
cd /d "%~dp0"

echo ========================================================
echo   Launching J.A.R.V.I.S. Native Desktop Application
echo ========================================================
echo.

cd frontend
call npm start
