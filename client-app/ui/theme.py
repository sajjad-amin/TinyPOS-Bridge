"""
Cross-Platform OS Dark Theme Detection.
Detects theme preferences across macOS, Windows (registry), and Linux (FreeDesktop XDG portal, GNOME, KDE Plasma).
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("tinypos.ui.theme")


def detect_system_dark_theme() -> bool:
    """Detect whether the host OS is using a dark theme (cross-platform)."""
    # 1. PyQt6 / Qt StyleHints check (supports macOS, Windows 10/11, and modern Linux via Freedesktop XDG portal)
    try:
        from PyQt6 import QtGui, QtCore
        hints = QtGui.QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == QtCore.Qt.ColorScheme.Dark:
                return True
            elif scheme == QtCore.Qt.ColorScheme.Light:
                return False
    except Exception:
        pass

    # 2. Qt Window Palette lightness check
    try:
        from PyQt6 import QtWidgets, QtGui
        app = QtWidgets.QApplication.instance()
        if app:
            pal = app.palette()
            col = pal.color(QtGui.QPalette.ColorRole.Window)
            if col.isValid() and col.lightness() < 128:
                return True
    except Exception:
        pass

    # 3. Linux-specific desktop environment checks (GNOME, KDE Plasma, GTK)
    if sys.platform.startswith("linux"):
        import os, subprocess
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return True

        # Check GNOME / FreeDesktop gsettings
        for cmd in [
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
        ]:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
                val = res.stdout.strip().lower()
                if "dark" in val or "prefer-dark" in val:
                    return True
            except Exception:
                pass

        # Check KDE Plasma config
        try:
            res = subprocess.run(
                ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
                capture_output=True, text=True, timeout=0.5
            )
            if "dark" in res.stdout.strip().lower():
                return True
        except Exception:
            pass

    # 4. Windows registry check (if not caught by Qt)
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
        except Exception:
            pass

    # 5. macOS defaults check (if not caught by Qt)
    if sys.platform == "darwin":
        try:
            import subprocess
            res = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, timeout=0.5)
            if "Dark" in res.stdout:
                return True
        except Exception:
            pass

    return False
