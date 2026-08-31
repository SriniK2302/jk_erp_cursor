@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
set JK_ERP_ENV=trial
echo.
echo JK ERP (trial):  http://127.0.0.1:8011/
echo Database: jk_erp_trial (or POSTGRES_DB from .env.trial)
echo Only user srini may sign in on this server.
echo Production server stays on port 8010 — run run_jk_erp.bat
echo.
python manage.py runserver 127.0.0.1:8011
