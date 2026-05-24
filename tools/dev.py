#!/usr/bin/env python3
"""
Development server for spicetify-remote.

Runs the server on an isolated port so it doesn't conflict with
a production server running as a service.

Features:
  - Auto-reloads when files change (server/, web/)
  - Separate dev config (data/config.dev.json)
  - Auto-patches extension to dev port on start, restores on exit

Usage:
    python tools/dev.py                        Start dev server with auto-reload
    python tools/dev.py --no-reload            Start without auto-reload
    python tools/dev.py --install-ext          Patch extension for dev port (manual)
    python tools/dev.py --restore-ext          Restore extension to prod port (manual)
    python tools/dev.py --port 7777            Custom dev port

Typical loop:
    # Start dev server (auto-patches extension, no manual steps needed)
    python tools/dev.py
    # ... make changes, server restarts automatically ...
    # Ctrl+C stops the server and restores the extension automatically
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEV_PORT = 8889

DEV_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.dev.json")
PROD_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.json")
SOURCE_EXT_PATH = os.path.join(PROJECT_ROOT, "spicetify-extension", "remoteVolume.js")
EXT_BACKUP_PATH = os.path.join(PROJECT_ROOT, "spicetify-extension", "remoteVolume.js.prod-backup")
WATCH_DIRS = [
    os.path.join(PROJECT_ROOT, "server"),
    os.path.join(PROJECT_ROOT, "web"),
]


def _get_spicetify_ext_dir():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.getenv("APPDATA", ""), "spicetify", "Extensions")
    elif system == "Linux":
        return os.path.expanduser("~/.config/spicetify/Extensions")
    elif system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/spicetify/Extensions")
    return None


def _read_port(config_path, default=8888):
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return int(json.load(f).get("port", default))
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    return default


def _read_port_from_file(filepath):
    try:
        with open(filepath) as f:
            m = re.search(r'DEFAULT_PORT:\s*(\d+)', f.read())
            if m:
                return int(m.group(1))
    except OSError:
        pass
    return None


def _write_dev_config(port, host):
    base = {}
    if os.path.exists(PROD_CONFIG_PATH):
        try:
            with open(PROD_CONFIG_PATH) as f:
                base = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    base["port"] = port
    base["host"] = host
    base["logLevel"] = "DEBUG"
    base.pop("_devMode", None)
    with open(DEV_CONFIG_PATH, "w") as f:
        json.dump(base, f, indent=2)


def _get_installed_ext_path():
    ext_dir = _get_spicetify_ext_dir()
    if not ext_dir:
        return None
    return os.path.join(ext_dir, "remoteVolume.js")


def _patch_ext_file(filepath, port, source_for_content=None):
    content = source_for_content
    if content is None:
        with open(filepath) as f:
            content = f.read()
    patched = re.sub(r'(DEFAULT_PORT:\s*)\d+', rf"\g<1>{port}", content)
    if patched == content:
        return False
    with open(filepath, "w") as f:
        f.write(patched)
    return True


def _spicetify_apply():
    try:
        result = subprocess.run(
            ["spicetify", "apply"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("  Spicetify: applied")
        else:
            print(f"  Spicetify: apply failed (stderr): {result.stderr.strip()}")
    except FileNotFoundError:
        print("  Spicetify: not found in PATH, skipping apply")
    except subprocess.TimeoutExpired:
        print("  Spicetify: apply timed out, skipping")
    except Exception as e:
        print(f"  Spicetify: apply error: {e}")


def _ensure_dev_ext(port):
    """Back up the installed extension and patch it to the dev port.
    If not yet installed, copy from source and install fresh.
    Returns True if Spicetify apply is needed."""
    installed = _get_installed_ext_path()
    ext_dir = _get_spicetify_ext_dir()
    if not installed or not ext_dir:
        print("  Extension: Spicetify Extensions directory not found")
        return False

    os.makedirs(ext_dir, exist_ok=True)

    if not os.path.exists(installed):
        print("  Extension: not yet installed, installing fresh")
        with open(SOURCE_EXT_PATH) as f:
            source_content = f.read()
        _patch_ext_file(installed, port, source_content)
        print(f"  Extension: installed and patched to port {port}")
        return True

    current_port = _read_port_from_file(installed)
    if current_port == port:
        print(f"  Extension: already on port {port}, no change needed")
        return False

    if not os.path.exists(EXT_BACKUP_PATH):
        shutil.copy2(installed, EXT_BACKUP_PATH)
        print(f"  Extension: backed up -> {EXT_BACKUP_PATH}")

    with open(SOURCE_EXT_PATH) as f:
        source_content = f.read()

    if not _patch_ext_file(installed, port, source_content):
        print("  Extension: WARNING could not patch DEFAULT_PORT")
        return False

    print(f"  Extension: patched to port {port}")
    return True


def _restore_prod_ext():
    """Restore the installed extension from backup. Removes backup afterwards."""
    if not os.path.exists(EXT_BACKUP_PATH):
        return

    installed = _get_installed_ext_path()
    if installed and os.path.exists(EXT_BACKUP_PATH):
        shutil.copy2(EXT_BACKUP_PATH, installed)

    os.remove(EXT_BACKUP_PATH)
    print("  Extension: restored from backup")


def _start_server(port, host, dev_config_path):
    env = os.environ.copy()
    env["SPICETIFY_CONFIG"] = dev_config_path
    proc = subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_ROOT, "server", "server.py")],
        env=env, cwd=PROJECT_ROOT,
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()


def _run_server_process(port, host, dev_config_path):
    """Top-level target for watchfiles.run_process (must be picklable on Windows)."""
    env = os.environ.copy()
    env["SPICETIFY_CONFIG"] = dev_config_path
    proc = subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_ROOT, "server", "server.py")],
        env=env, cwd=PROJECT_ROOT,
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()


def cmd_install_ext(args):
    port = args.port or DEFAULT_DEV_PORT
    ext_dir = _get_spicetify_ext_dir()
    if not ext_dir or not os.path.exists(ext_dir):
        print(f"Error: Spicetify Extensions directory not found at {ext_dir}")
        sys.exit(1)

    dest = os.path.join(ext_dir, "remoteVolume.js")
    if os.path.exists(dest) and not os.path.exists(EXT_BACKUP_PATH):
        shutil.copy2(dest, EXT_BACKUP_PATH)
        print(f"Saved production extension backup -> {EXT_BACKUP_PATH}")

    with open(SOURCE_EXT_PATH) as f:
        content = f.read()

    if not _patch_ext_file(dest, port, content):
        print(f"Warning: Could not patch DEFAULT_PORT in {SOURCE_EXT_PATH}")
        sys.exit(1)

    print(f"Extension installed -> port {port}")
    print("Restart Spotify or run 'spicetify apply' to pick up changes.")


def cmd_restore_ext(args):
    if not os.path.exists(EXT_BACKUP_PATH):
        port = _read_port(PROD_CONFIG_PATH, 8888)
        print(f"No backup found, restoring source to port {port} instead")
        if not _patch_ext_file(SOURCE_EXT_PATH, port):
            print(f"Warning: Could not patch DEFAULT_PORT in {SOURCE_EXT_PATH}")
        else:
            print(f"Source extension restored to port {port}")
        return

    ext_dir = _get_spicetify_ext_dir()
    if ext_dir:
        dest = os.path.join(ext_dir, "remoteVolume.js")
        shutil.copy2(EXT_BACKUP_PATH, dest)
        print(f"Extension restored -> {dest}")

    prod_port = _read_port(PROD_CONFIG_PATH, 8888)
    if not _patch_ext_file(SOURCE_EXT_PATH, prod_port):
        print(f"Warning: Could not patch DEFAULT_PORT in {SOURCE_EXT_PATH}")
    else:
        print(f"Source extension restored to port {prod_port}")
    os.remove(EXT_BACKUP_PATH)
    print(f"Removed backup: {EXT_BACKUP_PATH}")


def _run(port, host, no_reload=False):
    _write_dev_config(port, host)
    print(f"  Dev config: {DEV_CONFIG_PATH}")
    print(f"  Dev server: http://{host}:{port}/")
    print(f"  Data dir:   {os.path.join(PROJECT_ROOT, 'data')}")

    did_backup = _ensure_dev_ext(port)
    if did_backup:
        _spicetify_apply()

    def _cleanup():
        if did_backup:
            _restore_prod_ext()
            _spicetify_apply()
        if os.path.exists(DEV_CONFIG_PATH):
            os.remove(DEV_CONFIG_PATH)

    try:
        if no_reload:
            print("  Auto-reload: off")
            _start_server(port, host, DEV_CONFIG_PATH)
        else:
            try:
                from watchfiles import run_process
            except ImportError:
                print(
                    "Error: 'watchfiles' is required for auto-reload.\n"
                    "Install: pip install watchfiles\n"
                    "Or run:  python tools/dev.py --no-reload"
                )
                sys.exit(1)

            print("  Auto-reload: on (watching server/, web/)")
            print("  Press Ctrl+C to stop.")

            def callback(changes):
                print(f"  Reloading: {len(changes)} file(s) changed")

            run_process(*WATCH_DIRS, target=_run_server_process, args=(port, host, DEV_CONFIG_PATH), callback=callback)
    except KeyboardInterrupt:
        print("\nDev server stopped.")
    finally:
        _cleanup()


def main():
    parser = argparse.ArgumentParser(
        description="spicetify-remote development server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/dev.py                        Start dev server on port 8889
  python tools/dev.py --no-reload            Start without auto-reload
  python tools/dev.py --port 7777            Use port 7777

Auto-mode: patches extension to dev port on start, restores on exit.
Manual commands:
  python tools/dev.py --install-ext          Patch extension for dev port once
  python tools/dev.py --restore-ext          Restore extension to production port
        """,
    )

    parser.add_argument("--port", type=int, default=None,
                        help=f"Dev port (default: {DEFAULT_DEV_PORT})")
    parser.add_argument("--host", type=str, default=None,
                        help="Bind address (default: 127.0.0.1)")

    group = parser.add_argument_group("actions")
    group.add_argument("--no-reload", action="store_true",
                       help="Disable auto-reload on file changes")
    group.add_argument("--install-ext", action="store_true",
                       help="Patch Spicetify extension for the dev port (manual)")
    group.add_argument("--restore-ext", action="store_true",
                       help="Restore Spicetify extension to production port (manual)")

    args = parser.parse_args()

    if args.install_ext:
        cmd_install_ext(args)
    elif args.restore_ext:
        cmd_restore_ext(args)
    else:
        _run(args.port or DEFAULT_DEV_PORT, args.host or "127.0.0.1", no_reload=args.no_reload)


if __name__ == "__main__":
    main()
