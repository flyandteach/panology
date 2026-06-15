@echo off
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -q -r requirements.txt
streamlit run streamlit_app.py
pause
