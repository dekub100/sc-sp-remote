import os
import platform
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: Python executable not found: {sys.executable}")
        return False

def setup_extension():
    if not install_dependencies():
        print("\nWarning: Could not install Python dependencies automatically.")
        print("Please run: pip install aiohttp pywin32\n")

    system = platform.system()
    if system == "Windows":
        base_path = os.path.join(os.getenv('APPDATA'), 'spicetify')
    elif system == "Linux":
        base_path = os.path.expanduser('~/.config/spicetify')
    elif system == "Darwin":
        base_path = os.path.expanduser('~/Library/Application Support/spicetify')
    else:
        print(f"Error: Unsupported operating system: {system}")
        return

    extensions_path = os.path.join(base_path, 'Extensions')

    if not os.path.exists(extensions_path):
        os.makedirs(extensions_path, exist_ok=True)

    source_file = os.path.join(PROJECT_ROOT, "spicetify-extension", "remoteVolume.js")
    if not os.path.exists(source_file):
        print(f"Error: remoteVolume.js not found at {source_file}")
        return

    print(f"Copying remoteVolume.js to {extensions_path}...")
    shutil.copy(source_file, extensions_path)

    print("Registering extension with Spicetify...")
    if run_command(["spicetify", "config", "extensions", "remoteVolume.js"]):
        print("Applying Spicetify changes...")
        if run_command(["spicetify", "apply"]):
            print("\nSuccess! Spicetify extension installed and applied.")
            print("Make sure your server (python server/server.py) is running!")
        else:
            print("\nFailed to apply changes. Try running 'spicetify apply' manually.")
    else:
        print("\nFailed to register extension.")

if __name__ == "__main__":
    print(f"--- Spicetify Remote Setup ({platform.system()}) ---")
    setup_extension()
