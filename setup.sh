# ---- Start of Script ----

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting spicetify-remote installation..."
echo "---"

# Step 1: Clone the repository (if it doesn't already exist)
if [ ! -d "spicetify-remote" ]; then
    echo "Cloning the spicetify-remote repository..."
    git clone https://github.com/dekub100/spicetify-remote.git
else
    echo "Repository already exists. Skipping clone."
fi

# Step 2: Navigate to the repository directory
cd spicetify-remote

# Step 3: Install Node.js dependencies
echo "Installing Node.js dependencies with npm..."
npm install

# Step 4: Find the Spicetify extensions folder
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

# Step 5: Move the extension file to the Spicetify folder
echo "Moving remoteVolume.js to the extensions folder..."
cp remoteVolume.js "$EXTENSIONS_PATH/"

# Step 6: Add and apply the extension using Spicetify CLI
echo "Configuring Spicetify to use the extension..."
spicetify config extensions remoteVolume.js
spicetify apply

echo "---"
echo "Installation complete! You can now test it with 'node volume-server.js' from the spicetify-remote directory."

# ---- End of Script ----
