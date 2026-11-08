@echo off
set ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY_HERE
set GMAIL_APP_PASSWORD=YOUR_GMAIL_APP_PASSWORD_HERE
cd /d "%~dp0"
call venv\Scripts\activate.bat
python email_report.py
