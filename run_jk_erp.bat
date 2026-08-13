@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo JK ERP:  http://127.0.0.1:8010/
echo RTOM v2 uses port 8000 on this PC — do not use 8000 for JK ERP.
echo.
python manage.py runserver 127.0.0.1:8010
