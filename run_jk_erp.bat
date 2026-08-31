@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
set JK_ERP_ENV=production
echo.
echo JK ERP (production):  http://127.0.0.1:8010/
echo Database: jk_erp (or POSTGRES_DB from .env)
echo RTOM v2 uses port 8000 on this PC — do not use 8000 for JK ERP.
echo.
python manage.py runserver 127.0.0.1:8010
