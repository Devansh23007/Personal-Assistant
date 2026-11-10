@echo off
title V.I.P.E.R. Desktop Assistant
cd /d "%~dp0"

echo ========================================================
echo   Launching V.I.P.E.R. Native Desktop Application
echo ========================================================
echo.

cd frontend
call npm start
