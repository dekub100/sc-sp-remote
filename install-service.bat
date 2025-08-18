:: install-service.bat (for Windows - must be run as Administrator)
:: This script automates the installation of the server as a Windows service using NSSM.

@echo off
setlocal enabledelayedexpansion

:: Check for administrative privileges and elevate if necessary.
:: This prevents errors with service installation due to permissions.
>nul 2>&1 "%SystemRoot%\system32\cacls.exe" "%SystemRoot%\system32\config\system"
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~dpn0.bat' -Verb RunAs"
    exit /b
)

echo Starting Windows Service installation...
echo This script is now running with Administrator privileges.
echo.

:: Get the current directory of the script
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Step 1: Download and extract NSSM using PowerShell
echo Downloading and extracting NSSM...
powershell -command "& { try { Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'nssm.zip'; Expand-Archive -Path 'nssm.zip' -DestinationPath '.' -Force; Copy-Item -Path 'nssm-2.24\win64\nssm.exe' -Destination '.' -Force; Remove-Item -Path 'nssm.zip', 'nssm-2.24' -Recurse -Force; } catch { Write-Host 'Error: Failed to download or extract NSSM.'; Write-Host 'Check your internet connection and make sure PowerShell is working correctly.'; exit 1; } }"
if %errorlevel% neq 0 (
    echo An error occurred during the NSSM download/extraction. Exiting.
    pause
    exit /b 1
)
echo.

:: Step 2: Define service parameters
set "SERVICE_NAME=SpicetifyRemoteServer"
set "NODE_PATH="

:: Try to find Node.js path automatically in common locations
if exist "%ProgramFiles%\nodejs\node.exe" (
    set "NODE_PATH=%ProgramFiles%\nodejs\node.exe"
) else if exist "%ProgramFiles(x86)%\nodejs\node.exe" (
    set "NODE_PATH=%ProgramFiles(x86)%\nodejs\node.exe"
) else if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files\nodejs\node.exe"
) else if exist "C:\Program Files (x86)\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files (x86)\nodejs\node.exe"
) else (
    echo Error: Node.js executable not found automatically.
    echo Please manually enter the full path to your node.exe:
    set /p "NODE_PATH="
    if not exist "!NODE_PATH!" (
        echo Error: The provided path does not exist. Exiting.
        pause
        exit /b 1
    )
)

set "STARTUP_DIR=%SCRIPT_DIR%"
set "ARGUMENTS=volume-server.js"
set "FULL_SCRIPT_PATH=!STARTUP_DIR!!ARGUMENTS!"

echo Using Node.js path: "!NODE_PATH!"
echo.

:: Step 3: Install the service using NSSM
echo Installing the service: !SERVICE_NAME!
nssm.exe install "!SERVICE_NAME!" "!NODE_PATH!" "!FULL_SCRIPT_PATH!" AppDirectory "!STARTUP_DIR!"
echo.

echo ---
echo Service installation complete! The service is named "%SERVICE_NAME%".
echo To start it, you may need to go into the Services app and click "Start" or use "net start "%SERVICE_NAME%"" in a terminal.
echo Use the remove-service.bat script to remove it.
echo.

pause
endlocal
