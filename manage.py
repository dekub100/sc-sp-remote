#!/usr/bin/env python3
"""Management CLI for sc-sp-remote.

Usage:
    python manage.py run                                        Start production server
    python manage.py dev [--port N] [--host H] [--no-reload]    Dev server with auto-reload
    python manage.py install [spicetify|soundcloud]             Install extensions/plugins
    python manage.py service {install|update|start|stop|restart|remove}
                                                                Windows service management

Examples:
    python manage.py dev --port 7777        Dev server on custom port
    python manage.py install                Install both extensions
    python manage.py service install        Install + start Windows service
"""

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEV_PORT = 8888

DEV_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.dev.json")
PROD_CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config.json")
WATCH_DIRS = [
    os.path.join(PROJECT_ROOT, "server"),
    os.path.join(PROJECT_ROOT, "web"),
]
SERVER_SCRIPT = os.path.join(PROJECT_ROOT, "server", "server.py")

SERVICE_COMMANDS = ["install", "update", "start", "stop", "remove", "restart"]


# --- shared helpers -----------------------------------------------------------

def _get_spicetify_ext_dir():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "spicetify", "Extensions")
    elif system == "Linux":
        return os.path.expanduser("~/.config/spicetify/Extensions")
    elif system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/spicetify/Extensions")
    return None


def _run_command(command):
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


# --- run ----------------------------------------------------------------------

def cmd_run(args):
    proc = subprocess.Popen([sys.executable, SERVER_SCRIPT], cwd=PROJECT_ROOT)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()


# --- dev ----------------------------------------------------------------------

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


def _start_server(port, host, dev_config_path):
    env = os.environ.copy()
    env["SC_SP_REMOTE_CONFIG"] = dev_config_path
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
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
    import time

    os.environ["SC_SP_REMOTE_CONFIG"] = dev_config_path
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


def cmd_dev(args):
    port = args.port or DEFAULT_DEV_PORT
    host = args.host or "127.0.0.1"
    no_reload = args.no_reload
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
                    "Or run:  python manage.py dev --no-reload"
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


# --- install ------------------------------------------------------------------

def _install_dependencies():
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


def _install_spicetify_extension() -> None:
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
    if _run_command(["spicetify", "config", "extensions", "remoteVolume.js"]):
        print("Applying Spicetify changes...")
        if _run_command(["spicetify", "apply"]):
            print("\nSuccess! Spicetify extension installed and applied.")
        else:
            print("\nFailed to apply changes. Try running 'spicetify apply' manually.")
    else:
        print("\nFailed to register extension.")


def _install_soundcloud_plugin() -> None:
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


def cmd_install(args):
    if not _install_dependencies():
        print("\nWarning: Could not install Python dependencies automatically.")
        print("Please run: pip install aiohttp pywin32\n")

    if args.target == "spicetify":
        _install_spicetify_extension()
    elif args.target == "soundcloud":
        _install_soundcloud_plugin()
    else:
        print("Installing both extensions...")
        _install_spicetify_extension()
        print()
        _install_soundcloud_plugin()
        print()
        print("Done! Start the server with: python manage.py run")


# --- service (Windows only) ---------------------------------------------------

# Class must exist at module level: the pywin32 service host imports this
# module and resolves the registered class string "manage.ScSpRemoteService".
try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:
    ScSpRemoteService = None  # non-Windows or pywin32 not installed
else:
    class ScSpRemoteService(win32serviceutil.ServiceFramework):
        _svc_name_ = "ScSpRemotePython"
        _svc_display_name_ = "sc-sp-remote Server (Python)"
        _svc_description_ = "Relay server for sc-sp-remote"
        # Setting the default startup type to Automatic
        _svc_startup_type_ = win32service.SERVICE_AUTO_START

        def __init__(self, svc_args):
            win32serviceutil.ServiceFramework.__init__(self, svc_args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.process = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)
            if self.process:
                self.process.terminate()

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (self._svc_name_, ''))
            self.main()

        def main(self):
            python_exe = sys.executable
            if not python_exe.endswith("python.exe"):
                python_exe = os.path.join(os.path.dirname(python_exe), "python.exe")

            self.process = subprocess.Popen([python_exe, SERVER_SCRIPT], cwd=PROJECT_ROOT)
            crash_count = 0

            while True:
                rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
                if rc == win32event.WAIT_OBJECT_0:
                    break
                if self.process.poll() is not None:
                    crash_count += 1
                    backoff = min(5 * (2 ** (crash_count - 1)), 60)
                    servicemanager.LogMsg(servicemanager.EVENTLOG_ERROR_TYPE,
                                          0xF000,
                                          (f"Server process died (attempt {crash_count}). Restarting in {backoff}s...", ''))
                    time.sleep(backoff)
                    self.process = subprocess.Popen([python_exe, SERVER_SCRIPT], cwd=PROJECT_ROOT)
                else:
                    crash_count = 0

            if self.process:
                self.process.terminate()



def cmd_service(args):
    import win32service
    import win32serviceutil

    if ScSpRemoteService is None:
        sys.exit("Error: 'service' requires pywin32 (pip install pywin32)")

    command = args.action.lower()
    print("--- sc-sp-remote Service Tool ---")
    print(f"Executing: {command}...")

    # 'remove' only marks the service for deletion while it's running;
    # stop it first so the removal actually takes effect.
    if command == "remove" and ScSpRemoteService is not None:
        import pywintypes

        name = ScSpRemoteService._svc_name_
        try:
            win32serviceutil.StopService(name)
        except pywintypes.error:
            pass  # already stopped or not installed
        else:
            hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            hs = win32service.OpenService(hscm, name, win32service.SERVICE_QUERY_STATUS)
            deadline = time.time() + 30
            while time.time() < deadline:
                status = win32service.QueryServiceStatus(hs)
                if status[1] == win32service.SERVICE_STOPPED:
                    print("Service stopped.")
                    break
                time.sleep(0.5)
            else:
                print("Warning: service did not stop within 30s; removal may be deferred.")

    # HandleCommandLine parses sys.argv by default; feed it just the verb
    # since ours arrives as [manage.py, service, <action>].
    try:
        win32serviceutil.HandleCommandLine(ScSpRemoteService, argv=[sys.argv[0], command])

        # Manual override for Automatic startup
        if command == 'install':
            hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            hs = win32service.OpenService(hscm, ScSpRemoteService._svc_name_, win32service.SERVICE_CHANGE_CONFIG)
            win32service.ChangeServiceConfig(
                hs, win32service.SERVICE_NO_CHANGE,
                win32service.SERVICE_AUTO_START,
                win32service.SERVICE_NO_CHANGE, None, None, 0, None, None, None, None
            )
            print("Startup type forced to: Automatic")

            win32serviceutil.StartService(ScSpRemoteService._svc_name_)
            print("Service started.")

        print(f"\nSUCCESS: Command '{command}' completed.")
    except SystemExit as e:
        if e.code == 0:
            print(f"\nSUCCESS: Service '{command}' successful.")
        else:
            print(f"\nERROR: Service '{command}' failed with code {e.code}.")
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")


# --- entry point --------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    # Launched by the Windows SCM with no arguments: host the service.
    # If we're just a human running `python manage.py`, the dispatcher
    # connect fails and we fall through to printing help.
    if not argv:
        try:
            import servicemanager
            import win32service
        except ImportError:
            pass
        else:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(ScSpRemoteService)
            try:
                servicemanager.StartServiceCtrlDispatcher()
                return
            except win32service.error:
                pass  # not started by SCM — show help

    is_elevated = "--elevated" in argv
    if is_elevated:
        argv.remove("--elevated")

    parser = argparse.ArgumentParser(
        prog="python manage.py",
        description="sc-sp-remote management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage.py run                     Start production server
  python manage.py dev                     Dev server with auto-reload
  python manage.py dev --no-reload         Dev server without auto-reload
  python manage.py install                 Install both extensions
  python manage.py service install         Install + start Windows service
""",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Start production server (reads data/config.json)")
    p_run.set_defaults(func=cmd_run)

    p_dev = sub.add_parser("dev", help="Start dev server with auto-reload (isolated port/config)")
    p_dev.add_argument("--port", type=int, default=None,
                       help=f"Dev port (default: {DEFAULT_DEV_PORT})")
    p_dev.add_argument("--host", type=str, default=None,
                       help="Bind address (default: 127.0.0.1)")
    p_dev.add_argument("--no-reload", action="store_true",
                       help="Disable auto-reload on file changes")
    p_dev.set_defaults(func=cmd_dev)

    p_install = sub.add_parser("install", help="Install Python deps and extensions/plugins")
    p_install.add_argument("target", nargs="?", choices=["spicetify", "soundcloud"],
                           default=None, help="Install only this target (default: both)")
    p_install.set_defaults(func=cmd_install)

    p_service = sub.add_parser("service", help=f"Windows service management ({', '.join(SERVICE_COMMANDS)})")
    p_service.add_argument("action", choices=SERVICE_COMMANDS)
    p_service.set_defaults(func=cmd_service)

    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return

    # Service commands need admin; relaunch elevated like tools/service.py did.
    if args.cmd == "service" and not is_elevated:
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Requesting administrator privileges...")
                relaunch = ["python", os.path.abspath(__file__), "service", args.action, "--elevated"]
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(relaunch[1:]), None, 1)
                return
        except AttributeError:
            pass  # not Windows; let it fail naturally below

    args.func(args)

    # Elevated relaunch runs in a fresh console that would close instantly;
    # keep it open so the output is readable.
    if args.cmd == "service" and is_elevated:
        print("\n" + "=" * 40)
        print("Operation complete. Press Enter or wait 10 seconds to close...")
        try:
            import msvcrt
            deadline = time.time() + 10
            while time.time() < deadline:
                if msvcrt.kbhit():
                    msvcrt.getch()
                    break
                time.sleep(0.1)
        except (ImportError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
