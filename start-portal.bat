@echo off
REM Sobe a API e o portal em http://127.0.0.1:8000/portal/ (duplo clique neste arquivo).
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-portal.ps1" %*
echo.
echo A API foi encerrada.
pause
