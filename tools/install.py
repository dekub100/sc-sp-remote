import json
import os
import platform
import re
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.json")


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

    port = 8888
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            port = int(cfg.get("port", 8888))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Could not read config.json port, using default 8888: {e}")

    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()

    patched_content = re.sub(r'(DEFAULT_PORT:\s*)\d+', rf'\g<1>{port}', content)
    if patched_content == content:
        print(f"Warning: Could not patch DEFAULT_PORT in remoteVolume.js")

    dest_path = os.path.join(extensions_path, "remoteVolume.js")
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(patched_content)

    print(f"Extension patched to use port {port}")

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
