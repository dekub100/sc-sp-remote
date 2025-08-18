:: setup.bat (for Windows)
:: This script automates the installation of spicetify-remote on Windows.

@echo off
setlocal enabledelayedexpansion

echo Starting spicetify-remote installation...
echo ---

:: Step 0: Check for required dependencies
echo Checking for required dependencies: git, npm, and spicetify-cli...

:: Check for Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: 'git' is not installed.
    echo Please install Git from [https://git-scm.com/](https://git-scm.com/) and try again.
    exit /b 1
)

:: Check for npm
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: 'npm' is not installed.
    echo Please install Node.js (which includes npm) from [https://nodejs.org/](https://nodejs.org/) and try again.
    exit /b 1
)

:: Check for spicetify-cli
where spicetify >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: 'spicetify-cli' is not installed.
    echo Please install Spicetify by following the instructions at [https://spicetify.app/docs/getting-started/](https://spicetify.app/docs/getting-started/) before running this script.
    exit /b 1
)

echo All dependencies found. Proceeding with installation.

:: Step 1: Clone the repository (if it doesn't already exist)
if not exist "spicetify-remote" (
    echo Cloning the spicetify-remote repository...
    git clone [https://github.com/dekub100/spicetify-remote.git](https://github.com/dekub100/spicetify-remote.git)
) else (
    echo Repository already exists. Skipping clone.
)

:: Step 2: Navigate to the repository directory
cd spicetify-remote

:: Step 3: Install Node.js dependencies
echo Installing Node.js dependencies with npm...
npm install

:: Step 4: Find the Spicetify extensions folder.
:: This is a common location on Windows.
echo Finding Spicetify extensions folder...
set "EXTENSIONS_PATH=%userprofile%\.spicetify\Extensions"

if not exist "!EXTENSIONS_PATH!" (
    echo Could not automatically find Spicetify extensions folder.
    echo Please enter the full path to your Spicetify extensions directory:
    set /p "EXTENSIONS_PATH="
    if not exist "!EXTENSIONS_PATH!" (
        echo Error: The provided path does not exist. Exiting.
        exit /b 1
    )
)

echo Spicetify extensions folder found at: !EXTENSIONS_PATH!

:: Step 5: Move the extension file to the Spicetify folder
echo Moving remoteVolume.js to the extensions folder...
copy "remoteVolume.js" "!EXTENSIONS_PATH!"

:: Step 6: Add and apply the extension using Spicetify CLI
echo Configuring Spicetify to use the extension...
spicetify config extensions remoteVolume.js
spicetify apply

echo ---
echo Installation complete! You can now test it with 'node volume-server.js' from the spicetify-remote directory.

endlocal
