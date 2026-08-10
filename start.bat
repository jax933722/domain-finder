@echo off
REM ==========================================================================
REM  Domain Finder - one-click START (Windows)
REM  Double-click this file to build and launch the whole app with Docker.
REM ==========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo    Domain Finder - Starting
echo ==========================================================
echo.

REM --- Check Docker is installed ---
docker --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is not installed or not on your PATH.
  echo.
  echo Install Docker Desktop from:
  echo     https://docs.docker.com/get-docker/
  echo Then start Docker Desktop and run this file again.
  echo.
  pause
  exit /b 1
)

REM --- Check Docker Desktop is actually running ---
docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is installed but not running.
  echo Please start Docker Desktop, wait until it says "running", then try again.
  echo.
  pause
  exit /b 1
)

REM --- Check 'docker compose' is available ---
docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 'docker compose' is not available. Please update Docker Desktop.
  echo.
  pause
  exit /b 1
)

REM --- First run: create .env from the template ---
if not exist ".env" (
  echo First run detected: creating .env from .env.example ...
  copy ".env.example" ".env" >nul
  echo.
  echo  IMPORTANT: open the .env file and set at least:
  echo     SECRET_KEY, FIRST_ADMIN_EMAIL, FIRST_ADMIN_PASSWORD
  echo  Defaults will work for a quick local test, but change them before real use.
  echo.
)

echo Building and starting containers...
echo (The first run can take a few minutes while images download.)
echo.
docker compose up --build -d
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to start the containers. See the messages above.
  echo.
  pause
  exit /b 1
)

echo.
echo Waiting for the app to become ready...
set "STATUS="
set /a tries=0
:waitloop
timeout /t 3 /nobreak >nul
set "STATUS="
for /f %%A in ('curl -s -o nul -w "%%{http_code}" http://localhost:8080/health 2^>nul') do set "STATUS=%%A"
if "!STATUS!"=="200" goto ready
set /a tries+=1
if !tries! GEQ 25 goto ready
goto waitloop

:ready
echo.
echo ==========================================================
echo    Domain Finder is running!
echo ==========================================================
echo    App:      http://localhost:8080
echo    API docs: http://localhost:8080/docs
echo.
echo    To stop it later, double-click  stop.bat
echo ==========================================================
echo.
echo Opening the app in your browser...
start "" http://localhost:8080
echo.
pause
endlocal
