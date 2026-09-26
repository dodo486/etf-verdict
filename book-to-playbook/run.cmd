@echo off
REM Windows 래퍼 - 작업 스케줄러에서 이 파일을 호출한다.
REM   run.cmd            (EOD)
REM   run.cmd intraday   (장중)
setlocal
set "DIR=%~dp0"
if "%BOOK_TO_PLAYBOOK_PYTHON%"=="" (set "PY=python") else (set "PY=%BOOK_TO_PLAYBOOK_PYTHON%")
if "%~1"=="" (set "MODE=daily") else (set "MODE=%*")
"%PY%" "%DIR%run.py" %MODE%
exit /b %ERRORLEVEL%
