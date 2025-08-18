:: remove-service.bat (for Windows - must be run as Administrator)
:: This script removes the Windows service created by install-service.bat.

@echo off
setlocal enabledelayedexpansion

:: Check for administrative privileges and elevate if necessary.
>nul 2>&1 "%SystemRoot%\system32\cacls.exe" "%SystemRoot%\system32\config\system"
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~dpn0.bat' -Verb RunAs"
    exit /b
)

echo Starting Windows Service removal...
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

:: Define the service name
set "SERVICE_NAME=SpicetifyRemoteServer"

:: Step 2: Stop the service (if it's running)
echo Stopping the service: !SERVICE_NAME!
sc query "!SERVICE_NAME!" | find "RUNNING" >nul
if %errorlevel% equ 0 (
    net stop "!SERVICE_NAME!"
    echo.
) else (
    echo Service is not running.
    echo.
)

:: Step 3: Remove the service using NSSM
echo Removing the service: !SERVICE_NAME!
nssm.exe remove "!SERVICE_NAME!" confirm
echo.

echo ---
echo Service removal complete!
echo.

pause
endlocal
