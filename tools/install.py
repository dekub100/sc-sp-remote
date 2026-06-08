"""Install tools for sc-sp-remote."""
from __future__ import annotations

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


def _get_spicetify_ext_dir():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "spicetify", "Extensions")
    elif system == "Linux":
        return os.path.expanduser("~/.config/spicetify/Extensions")
    elif system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/spicetify/Extensions")
    return None


def install_spicetify_extension() -> None:
    spicetify_dir = _get_spicetify_ext_dir()
    if not spicetify_dir or not os.path.exists(spicetify_dir):
        print(f"Spicetify extensions directory not found: {spicetify_dir}")
        print("Make sure Spicetify is installed.")
        return

    src = os.path.join(PROJECT_ROOT, "spicetify-extension", "remoteVolume.js")
    dst = os.path.join(spicetify_dir, "remoteVolume.js")

    if os.path.exists(dst):
        print(f"Extension already exists at {dst}")
        overwrite = input("Overwrite? (y/n): ").strip().lower()
        if overwrite != "y":
            print("Skipped.")
            return

    shutil.copy2(src, dst)
    print(f"Installed Spicetify extension to: {dst}")

    print("Registering extension with Spicetify...")
    if run_command(["spicetify", "config", "extensions", "remoteVolume.js"]):
        print("Applying Spicetify changes...")
        if run_command(["spicetify", "apply"]):
            print("\nSuccess! Spicetify extension installed and applied.")
        else:
            print("\nFailed to apply changes. Try running 'spicetify apply' manually.")
    else:
        print("\nFailed to register extension.")


def install_soundcloud_plugin() -> None:
    sc_dir = os.path.join(os.environ.get("APPDATA", ""), "soundcloud-rpc", "plugins")
    if not os.path.exists(sc_dir):
        print(f"soundcloud-rpc plugins directory not found: {sc_dir}")
        print("Make sure soundcloud-rpc is installed.")
        return

    src = os.path.join(PROJECT_ROOT, "soundcloud-plugin", "soundcloud-remote-bridge.js")
    dst = os.path.join(sc_dir, "soundcloud-remote-bridge.js")

    if os.path.exists(dst):
        print(f"Plugin already exists at {dst}")
        overwrite = input("Overwrite? (y/n): ").strip().lower()
        if overwrite != "y":
            print("Skipped.")
            return

    shutil.copy2(src, dst)
    print(f"Installed SoundCloud plugin to: {dst}")
    print("Restart soundcloud-rpc to load the plugin.")


def main() -> None:
    if not install_dependencies():
        print("\nWarning: Could not install Python dependencies automatically.")
        print("Please run: pip install aiohttp pywin32\n")

    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
        if target == "spicetify":
            install_spicetify_extension()
        elif target == "soundcloud":
            install_soundcloud_plugin()
        else:
            print(f"Unknown target: {target}")
            print("Usage: python tools/install.py [spicetify|soundcloud]")
    else:
        print("Installing both extensions...")
        install_spicetify_extension()
        print()
        install_soundcloud_plugin()
        print()
        print("Done! Start the server with: python server/server.py")


if __name__ == "__main__":
    main()
