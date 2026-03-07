"""
Windows service wrapper for vault-mcp server.

Usage (run as Administrator):
    python service.py --startup delayed install
    python service.py start
    python service.py stop
    python service.py debug
    python service.py remove
"""

import os
import sys
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

# Directory containing this file (vault-mcp/)
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_SERVICE_DIR, "src")


class VaultMCPService:
    """Business logic for starting/stopping the vault-mcp server."""

    def __init__(self):
        self._thread: threading.Thread | None = None

    def run(self):
        os.chdir(_SERVICE_DIR)
        if _SRC_DIR not in sys.path:
            sys.path.insert(0, _SRC_DIR)

        import server
        self._thread = threading.current_thread()
        server.main()

    def stop(self):
        # server module is already imported if run() was called
        if "server" in sys.modules:
            sys.modules["server"].shutdown()


class VaultMCPServiceFramework(win32serviceutil.ServiceFramework):
    _svc_name_ = "VaultMCPServer"
    _svc_display_name_ = "Vault MCP Server"
    _svc_description_ = (
        "MCP server providing cached access to Obsidian vault tasks and efforts"
    )

    def __init__(self, args):
        super().__init__(args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._impl = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{self._svc_name_} stopping...")
        if self._impl:
            self._impl.stop()
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        servicemanager.LogInfoMsg(f"{self._svc_name_} starting...")

        self._impl = VaultMCPService()
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        try:
            self._impl.run()
        except Exception as exc:
            servicemanager.LogErrorMsg(f"{self._svc_name_} error: {exc}")
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)


def init():
    if len(sys.argv) == 1:
        # Started by the Windows SCM
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(VaultMCPServiceFramework)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(VaultMCPServiceFramework)


if __name__ == "__main__":
    init()
