@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import aiogram, yaml" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 goto error
goto done
:error
echo.
echo Не удалось запустить бота. Проверьте Python, интернет и конфиг клиента.
pause
:done
