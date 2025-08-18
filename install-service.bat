:: install-service.bat (for Windows - must be run as Administrator)
:: This script automates the installation of the server as a Windows service using NSSM.

@echo off
setlocal enabledelayedexpansion

echo Starting Windows Service installation...
echo This script must be run with Administrator privileges.

:: Get the current directory of the script
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Step 1: Download NSSM
echo Downloading NSSM...
powershell -command "& { iwr [https://nssm.cc/download](https://nssm.cc/download) -o nssm.zip }"
tar -xf nssm.zip -C "%SCRIPT_DIR%" --strip-components=1 nssm-2.24/win64/nssm.exe
del nssm.zip

:: Step 2: Define service parameters
set "SERVICE_NAME=SpicetifyRemoteServer"
set "NODE_PATH=C:\Program Files\nodejs\node.exe" :: Default Node.js path, you might need to change this
set "STARTUP_DIR=%SCRIPT_DIR%"
set "ARGUMENTS=volume-server.js"

:: Check if Node.js path exists
if not exist "!NODE_PATH!" (
    echo Error: Node.js executable not found at "!NODE_PATH!"
    echo Please update the "NODE_PATH" variable in this script with the correct path.
    pause
    exit /b 1
)

:: Step 3: Install the service using NSSM
echo Installing the service: !SERVICE_NAME!
nssm.exe install "!SERVICE_NAME!" "!NODE_PATH!" "!ARGUMENTS!"
nssm.exe set "!SERVICE_NAME!" AppDirectory "!STARTUP_DIR!"

echo ---
echo Service installation complete! The service is named "%SERVICE_NAME%".
echo It will automatically start when the computer boots up.
echo To start it manually, use "net start "%SERVICE_NAME%"" in a terminal.
echo Use "remove-service.bat" to remove it.

pause
endlocal
```batch
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
