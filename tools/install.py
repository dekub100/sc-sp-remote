"""Install tools for sc-spotify-remote."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_spicetify_extension() -> None:
    """Copy the Spicetify extension to the Spicetify Extensions directory."""
    spicetify_dir = os.path.join(os.environ.get("APPDATA", ""), "spicetify", "Extensions")
    if not os.path.exists(spicetify_dir):
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

    # Auto-patch port
    config_path = os.path.join(PROJECT_ROOT, "data", "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        port = config.get("port", 8889)

        with open(dst, "r") as f:
            content = f.read()
        content = re.sub(r"DEFAULT_PORT:\s*\d+", f"DEFAULT_PORT: {port}", content)
        with open(dst, "w") as f:
            f.write(content)
        print(f"Patched extension port to {port}")


def install_soundcloud_plugin() -> None:
    """Copy the SoundCloud plugin to the soundcloud-rpc plugins directory."""
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
