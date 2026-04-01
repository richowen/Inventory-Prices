@echo off
setlocal

set SCRIPT_DIR=%~dp0
set PS1=%SCRIPT_DIR%deploy_from_home.ps1

if not exist "%PS1%" (
  echo [deploy] ERROR: PowerShell script not found: "%PS1%"
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -PiHost "farmprices.west-stonecat.ts.net" -PiUser "richowen" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo [deploy] FAILED with exit code %EXITCODE%
  exit /b %EXITCODE%
)

echo [deploy] Completed successfully
exit /b 0
