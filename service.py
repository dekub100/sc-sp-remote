import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import subprocess
import time
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class SpicetifyRemoteService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SpicetifyRemotePython"
    _svc_display_name_ = "Spicetify Remote Server (Python)"
    _svc_description_ = "Relay server for Spicetify remote control and OBS widget"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
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
        base_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(base_dir, "server.py")
        
        python_exe = sys.executable
        if not python_exe.endswith("python.exe"):
            python_exe = os.path.join(os.path.dirname(python_exe), "python.exe")

        self.process = subprocess.Popen([python_exe, script_path], cwd=base_dir)
        
        while True:
            rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break
            if self.process.poll() is not None:
                servicemanager.LogMsg(servicemanager.EVENTLOG_ERROR_TYPE,
                                      0xF000,
                                      ("Server process died unexpectedly. Restarting...", ''))
                self.process = subprocess.Popen([python_exe, script_path], cwd=base_dir)

        if self.process:
            self.process.terminate()

if __name__ == '__main__':
    is_elevated_process = "--elevated" in sys.argv
    if is_elevated_process:
        sys.argv.remove("--elevated")

    # Request admin privileges if not already admin
    if len(sys.argv) > 1 and sys.argv[1] in ['install', 'update', 'start', 'stop', 'remove', 'restart']:
        if not is_admin():
            print("Requesting administrator privileges...")
            args = sys.argv[:]
            args.append("--elevated")
            # Re-run the script as administrator
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(args), None, 1)
            sys.exit()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        print(f"--- Spicetify Remote Service Tool ---")
        print(f"Executing: {command}...")
        
        try:
            # win32serviceutil.HandleCommandLine handles the heavy lifting
            # but it usually calls sys.exit(). We'll try to catch it to show a message.
            win32serviceutil.HandleCommandLine(SpicetifyRemoteService)
            print(f"\nSUCCESS: Command '{command}' completed.")
        except SystemExit as e:
            if e.code == 0:
                print(f"\nSUCCESS: Service '{command}' successful.")
            else:
                print(f"\nERROR: Service '{command}' failed with code {e.code}.")
        except Exception as e:
            print(f"\nCRITICAL ERROR: {e}")

        # If we were in an elevated window, keep it open so the user can see the result
        if is_elevated_process:
            print("\n" + "="*40)
            print("Operation complete. Press Enter to close this window.")
            input()
    else:
        # Standard service start (triggered by Windows SCM)
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SpicetifyRemoteService)
        servicemanager.StartServiceCtrlDispatcher()
