#!/usr/bin/env python3
"""
Development server for sc-sp-remote.

Runs the server on an isolated port so it doesn't conflict with
a production server running as a service.

Features:
  - Auto-reloads when files change (server/, web/)
  - Separate dev config (data/config.dev.json)

Usage:
    python tools/dev.py                        Start dev server with auto-reload
    python tools/dev.py --no-reload            Start without auto-reload

Typical loop:
    # Start dev server
    python tools/dev.py
    # ... make changes, server restarts automatically ...
    # Ctrl+C to stop
"""

import argparse
import json
import os
import platform
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEV_PORT = 8888

DEV_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.dev.json")
PROD_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.json")
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


def _start_server(port, host, dev_config_path):
    env = os.environ.copy()
    env["SC_REMOTE_CONFIG"] = dev_config_path
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
    """Top-level target for watchfiles.run_process.
    Runs server directly (no subprocess) so TerminateProcess kills everything.
    Retries on bind failure (port-release race)."""
    import asyncio
    import sys
    import time

    os.environ["SC_REMOTE_CONFIG"] = dev_config_path
    server_dir = os.path.join(PROJECT_ROOT, "server")
    sys.path.insert(0, server_dir)
    import server

    for attempt in range(5):
        try:
            asyncio.run(server.main())
            return
        except KeyboardInterrupt:
            return
        except OSError:
            if attempt < 4:
                delay = 0.5 * (attempt + 1)
                print(f"  Server: bind failed, retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def _run(port, host, no_reload=False):
    _write_dev_config(port, host)
    print(f"  Dev config: {DEV_CONFIG_PATH}")
    print(f"  Dev server: http://{host}:{port}/")
    print(f"  Data dir:   {os.path.join(PROJECT_ROOT, 'data')}")

    def _cleanup():
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
        description="sc-sp-remote development server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/dev.py                        Start dev server on port 8888
  python tools/dev.py --no-reload            Start without auto-reload
  python tools/dev.py --port 7777            Use port 7777
        """,
    )

    parser.add_argument("--port", type=int, default=None,
                        help=f"Dev port (default: {DEFAULT_DEV_PORT})")
    parser.add_argument("--host", type=str, default=None,
                        help="Bind address (default: 127.0.0.1)")

    parser.add_argument("--no-reload", action="store_true",
                        help="Disable auto-reload on file changes")

    args = parser.parse_args()
    _run(args.port or DEFAULT_DEV_PORT, args.host or "127.0.0.1", no_reload=args.no_reload)


if __name__ == "__main__":
    main()
