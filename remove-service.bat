:: remove-service.bat (for Windows - must be run as Administrator)
:: This script removes the Windows service created by install-service.bat.

@echo off
setlocal enabledelayedexpansion

echo Starting Windows Service removal...
echo This script must be run with Administrator privileges.

:: Define the service name
set "SERVICE_NAME=SpicetifyRemoteServer"

:: Step 1: Stop the service (if it's running)
echo Stopping the service: !SERVICE_NAME!
net stop "!SERVICE_NAME!"

:: Step 2: Remove the service using NSSM
echo Removing the service: !SERVICE_NAME!
nssm.exe remove "!SERVICE_NAME!" confirm

echo ---
echo Service removal complete!

pause
endlocal
