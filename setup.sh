# setup.sh (for Linux/macOS)
# This script automates the installation of spicetify-remote.

# ---- Start of Script ----

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting spicetify-remote installation..."
echo "==========================================="
echo ""

# Step 0: Check for required dependencies
echo "Checking for required dependencies..."

# Check for Git
if ! command -v git &> /dev/null
then
    echo "Error: 'git' is not installed."
    echo "Please install Git and run this script again."
    echo "On Debian/Ubuntu: sudo apt-get install git"
    echo "On Fedora/CentOS: sudo dnf install git"
    echo "On macOS with Homebrew: brew install git"
    exit 1
fi

# Check for npm
if ! command -v npm &> /dev/null
then
    echo "Error: 'npm' is not installed."
    echo "Please install npm (part of Node.js) and run this script again."
    echo "On most systems, you can download Node.js from https://nodejs.org/"
    exit 1
fi

# Check for spicetify-cli
if ! command -v spicetify &> /dev/null
then
    echo "Error: 'spicetify-cli' is not installed."
    echo "Please install Spicetify by following the instructions at https://spicetify.app/docs/getting-started/ before running this script."
    echo "Also see https://spicetify.app/docs/advanced-usage/installation#note-for-linux-users"
    exit 1
fi

echo "All dependencies found."
echo ""
echo "==========================================="
echo ""

# Step 1: Install Node.js dependencies
echo "Installing Node.js dependencies with npm..."
npm install
echo ""

# Step 2: Find the Spicetify extensions folder
# The location can vary, so we'll try a few common paths.
echo "Finding Spicetify extensions folder..."
if [ -d "$HOME/.config/spicetify/Extensions" ]; then
    EXTENSIONS_PATH="$HOME/.config/spicetify/Extensions"
elif [ -d "$HOME/.config/spicetify/extensions" ]; then
    EXTENSIONS_PATH="$HOME/.config/spicetify/extensions"
else
    echo "Could not automatically find Spicetify extensions folder."
    echo "Please enter the full path to your Spicetify extensions directory:"
    read -r EXTENSIONS_PATH
    if [ ! -d "$EXTENSIONS_PATH" ]; then
        echo "Error: The provided path does not exist. Exiting."
        exit 1
    fi
fi

echo "Spicetify extensions folder found at: $EXTENSIONS_PATH"
echo ""

# Step 3: Move the extension file to the Spicetify folder
echo "Moving remoteVolume.js to the extensions folder..."
cp remoteVolume.js "$EXTENSIONS_PATH/"
echo ""

# Step 4: Add and apply the extension using Spicetify CLI
echo "Configuring Spicetify to use the extension..."
spicetify config extensions remoteVolume.js
spicetify apply
echo ""

echo "==========================================="
echo "Installation complete! You can now test it with 'node volume-server.js' from this directory."
echo "Press Enter to exit."
read -r
exit 0
