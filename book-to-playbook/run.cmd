@echo off
REM Windows 래퍼 - 작업 스케줄러에서 이 파일을 호출한다.
REM   run.cmd            (EOD)
setlocal
set "DIR=%~dp0"
if "%BOOK_TO_PLAYBOOK_PYTHON%"=="" (set "PY=python") else (set "PY=%BOOK_TO_PLAYBOOK_PYTHON%")
if "%~1"=="" (set "MODE=daily") else (set "MODE=%*")
cd /d "%DIR%"
"%PY%" -m orchestration.run %MODE%
exit /b %ERRORLEVEL%
