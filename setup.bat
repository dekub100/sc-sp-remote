@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Spicetify Remote - Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo [OK] Found %PYVER%
echo.

:: Install dependencies
echo Installing Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.

:: Create data directory and default config if missing
if not exist "data" (
    echo Creating data directory...
    mkdir data
)

if not exist "data\config.json" (
    echo Creating default config.json...
    (
        echo {
        echo   "port": 8888,
        echo   "allowedOrigins": ["*"],
        echo   "defaultVolume": 0.5,
        echo   "enableOBS": true,
        echo   "enableWebsite": true,
        echo   "volumeStep": 0.05,
        echo   "logLevel": "INFO",
        echo   "backupCount": 3,
        echo   "maxQueueSize": 50,
        echo   "queueRateLimitSeconds": 30
        echo }
    ) > data\config.json
    echo [OK] Default config created at data\config.json
) else (
    echo [OK] config.json already exists
)
echo.

:: Install Spicetify extension
echo Installing Spicetify extension...
python tools\install.py
echo.

:: Ask about Windows service
echo ============================================
echo   Optional: Install as Windows Service?
echo ============================================
echo This runs the server automatically at startup.
echo Requires administrator privileges.
echo.
set /p INSTALL_SERVICE="Install service? (y/N): "

if /i "%INSTALL_SERVICE%"=="y" (
    echo.
    echo Installing Windows service...
    python tools\service.py install
    if %errorlevel% equ 0 (
        python tools\service.py start
        echo [OK] Service installed and started.
    ) else (
        echo [WARN] Service install failed. You can still run the server manually.
    )
) else (
    echo Skipping service installation.
    echo To start the server manually: python server\server.py
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Config:  data\config.json
echo Logs:    data\logs\
echo State:   data\state.json
echo.
echo To start the server manually:
echo   python server\server.py
echo.
pause
