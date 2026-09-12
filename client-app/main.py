#!/usr/bin/env python3
"""
TinyPOS Desktop Client Application
Menu Bar / System Tray Bridge for Bluetooth Thermal Printers.
"""

import logging
import os
import sys
import traceback
from pathlib import Path

# Ensure client-app directory is in python path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Ensure log directory exists
LOG_DIR = Path.home() / ".tinypos_client"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
LOG_FILE = LOG_DIR / "client.log"

# Setup logging handlers safely (handling None stdout in windowed GUI binaries)
handlers = []
try:
    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    handlers.append(file_handler)
except Exception:
    pass

if sys.stdout is not None:
    try:
        handlers.append(logging.StreamHandler(sys.stdout))
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=handlers if handlers else [logging.NullHandler()],
)

logger = logging.getLogger("tinypos.client")


def show_fatal_error_dialog(title: str, message: str):
    """Display a native OS dialog if an unhandled startup crash occurs."""
    logger.critical(f"FATAL ERROR: {title} - {message}")

    if sys.platform == "win32":
        try:
            import ctypes
            # MB_ICONERROR (0x10) | MB_OK (0x0)
            ctypes.windll.user32.MessageBoxW(0, f"{message}\n\nTraceback logged to:\n{LOG_FILE}", title, 0x10)
            return
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, f"{message}\n\nTraceback logged to:\n{LOG_FILE}")
        root.destroy()
    except Exception:
        pass


def uncaught_exception_handler(exc_type, exc_value, exc_traceback):
    """Global hook for unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical(f"Uncaught Exception:\n{err_msg}")
    show_fatal_error_dialog("TinyPOS Startup Error", f"An unexpected error occurred:\n{exc_value}")


sys.excepthook = uncaught_exception_handler

_instance_lock_socket = None


def acquire_single_instance_lock(port: int = 49281) -> bool:
    """Ensure only one instance of TinyPOS client runs at a time via loopback socket."""
    global _instance_lock_socket
    import socket
    try:
        _instance_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _instance_lock_socket.bind(("127.0.0.1", port))
        return True
    except (socket.error, OSError):
        return False


def main():
    if not acquire_single_instance_lock():
        logger.warning("Another instance of TinyPOS Client is already running. Exiting duplicate process.")
        sys.exit(0)

    logger.info(f"Initializing TinyPOS Desktop Client on {sys.platform}...")

    if sys.platform == "darwin":
        from core.tray_mac import run_mac_app
        run_mac_app()
    else:
        from core.tray_crossplatform import run_crossplatform_app
        run_crossplatform_app()


if __name__ == "__main__":
    main()

