:: setup.bat (for Windows)
:: This script automates the installation of spicetify-remote on Windows.
:: This version has improved user feedback and a cleaner display.

@echo off
setlocal enabledelayedexpansion

echo Starting spicetify-remote installation...
echo ===========================================
echo.

:: Step 0: Check for required dependencies
echo Checking for required dependencies...

:: The PowerShell command is run silently, so it won't clutter the output.
powershell -command "function Check-Dependency{param([string]$Name,[string]$Command,[string]$InstallMsg);if(-not(Get-Command -Name $Command -ErrorAction SilentlyContinue)){Write-Host 'Error:' $Name 'is not installed.';Write-Host $InstallMsg;exit 1;}};Check-Dependency 'git' 'git.exe' 'Please install Git from https://git-scm.com/ and try again.';Check-Dependency 'npm' 'npm.cmd' 'Please install Node.js (which includes npm) from https://nodejs.org/ and try again.';Check-Dependency 'spicetify-cli' 'spicetify.exe' 'Please install Spicetify by following the instructions at https://spicetify.app/docs/getting-started/ before running this script.'"
if %errorlevel% neq 0 (
    echo.
    echo An error was found during the dependency check.
    echo Please resolve the issues listed above and run the script again.
    pause
    exit /b 1
)

echo All dependencies found.
echo.
echo ===========================================
echo.

:: Step 1: Install Node.js dependencies
echo Installing Node.js dependencies with npm...
call npm install
if %errorlevel% neq 0 (
    echo.
    echo Error: The 'npm install' command failed.
    echo This could be due to a network issue or a permissions problem.
    echo Try running the script again, or check the npm logs for more details.
    pause
    exit /b 1
)
echo.

:: Step 2: Find the Spicetify extensions folder.
echo Finding Spicetify extensions folder...
set "EXTENSIONS_PATH=%AppData%\spicetify\Extensions"
if not exist "!EXTENSIONS_PATH!" (
    echo Could not automatically find Spicetify extensions folder.
    echo Please enter the full path to your Spicetify extensions directory:
    set /p "EXTENSIONS_PATH="
    if not exist "!EXTENSIONS_PATH!" (
        echo Error: The provided path does not exist. Exiting.
        pause
        exit /b 1
    )
)
echo Spicetify extensions folder found at: !EXTENSIONS_PATH!
echo.

:: Step 3: Move the extension file to the Spicetify folder
echo Moving remoteVolume.js to the extensions folder...
copy "remoteVolume.js" "!EXTENSIONS_PATH!"
echo.

:: Step 4: Add and apply the extension using Spicetify CLI
echo Configuring Spicetify to use the extension...
spicetify config extensions remoteVolume.js
spicetify apply
echo.

echo ===========================================
echo Installation complete! You can now test it with 'node volume-server.js' from this directory.
pause
endlocal
