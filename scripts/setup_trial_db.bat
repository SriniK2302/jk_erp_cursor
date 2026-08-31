@echo off
setlocal
cd /d "%~dp0.."
call venv\Scripts\activate.bat
set JK_ERP_ENV=trial

echo.
echo Setting up JK ERP trial database...
echo.

python manage.py setup_trial_db
if errorlevel 1 exit /b 1

echo.
echo Next steps:
echo   1. Create the srini user if needed:
echo        set JK_ERP_ENV=trial
echo        python manage.py createsuperuser --username srini
echo   2. Start the trial server:
echo        run_jk_erp_trial.bat
echo.
