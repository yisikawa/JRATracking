@echo off
chcp 65001 > nul
setlocal

echo [JRA Tracking App] 起動中...
echo.

cd /d %~dp0
call venv\Scripts\activate

echo Streamlitを起動しています (ポート 8501)...
echo アプリケーションを終了するには Ctrl+C を押してください...
echo.

streamlit run main.py
