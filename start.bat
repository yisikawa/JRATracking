@echo off
setlocal

cd /d %~dp0
call venv\Scripts\activate

start "JRA Backend" cmd /k "cd /d %~dp0 && call venv\Scripts\activate && uvicorn backend.main:app --port 8000 --reload"

timeout /t 2 /nobreak > nul

start "JRA Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev"

echo.
echo ========================================
echo  JRA Tracking App started
echo  Open http://localhost:5151
echo ========================================
echo.
pause
