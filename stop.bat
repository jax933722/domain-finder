@echo off
REM ==========================================================================
REM  Domain Finder - one-click STOP (Windows)
REM  Double-click this file to stop the app. Your data is preserved.
REM ==========================================================================
setlocal
cd /d "%~dp0"

echo ==========================================================
echo    Domain Finder - Stopping
echo ==========================================================
echo.

docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is not available. Is Docker Desktop installed and running?
  echo.
  pause
  exit /b 1
)

docker compose down
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to stop cleanly. Make sure Docker Desktop is running.
  echo.
  pause
  exit /b 1
)

echo.
echo ==========================================================
echo    Domain Finder stopped. Your data has been kept.
echo ==========================================================
echo.
echo    Tip: to ALSO erase all data (users, jobs, cache) and start
echo    completely fresh next time, run this command once:
echo        docker compose down -v
echo.
pause
endlocal
