import os
import shutil
import subprocess
import sys
import platform

def run_command(command):
    print(f"Running: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Is Spicetify installed and in your PATH?")
        return False

def install_dependencies():
    print("Checking for required Python packages...")
    try:
        # Check if we have requirements.txt
        if os.path.exists("requirements.txt"):
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        else:
            # Fallback if requirements.txt is missing
            packages = ["aiohttp", "websockets"]
            if platform.system() == "Windows":
                packages.append("pywin32")
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def setup_extension():
    # 0. Install Python dependencies
    if not install_dependencies():
        print("\nWarning: Could not install Python dependencies automatically.")
        print("Please run: pip install aiohttp websockets pywin32\n")

    # 1. Determine Spicetify path based on OS
    system = platform.system()
    if system == "Windows":
        base_path = os.path.join(os.getenv('APPDATA'), 'spicetify')
    elif system == "Linux":
        base_path = os.path.expanduser('~/.config/spicetify')
    elif system == "Darwin": # macOS
        base_path = os.path.expanduser('~/Library/Application Support/spicetify')
    else:
        print(f"Error: Unsupported operating system: {system}")
        return

    extensions_path = os.path.join(base_path, 'Extensions')
    
    if not os.path.exists(extensions_path):
        os.makedirs(extensions_path, exist_ok=True)

    # 2. Copy remoteVolume.js to Extensions folder
    source_file = "remoteVolume.js"
    if not os.path.exists(source_file):
        print(f"Error: {source_file} not found in current directory.")
        return

    print(f"Copying {source_file} to {extensions_path}...")
    shutil.copy(source_file, extensions_path)

    # 3. Register the extension
    print("Registering extension with Spicetify...")
    if run_command(["spicetify", "config", "extensions", source_file]):
        # 4. Apply changes
        print("Applying Spicetify changes...")
        if run_command(["spicetify", "apply"]):
            print("\nSuccess! Spicetify extension installed and applied.")
            print("Make sure your server (python server.py) is running!")
        else:
            print("\nFailed to apply changes. Try running 'spicetify apply' manually.")
    else:
        print("\nFailed to register extension.")

if __name__ == "__main__":
    print(f"--- Spicetify Remote Setup ({platform.system()}) ---")
    setup_extension()
