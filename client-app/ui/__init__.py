"""
UI Package for TinyPOS Client.
Modular components for cross-platform themes, styles, settings dialogs, and tray applications.
"""

from __future__ import annotations

from .theme import detect_system_dark_theme
from .styles import get_qt_dialog_stylesheet
from .qt_settings import QtSettingsDialog, PYQT_AVAILABLE
from .tk_settings import TkSettingsWindow, TK_AVAILABLE

__all__ = [
    "detect_system_dark_theme",
    "get_qt_dialog_stylesheet",
    "QtSettingsDialog",
    "PYQT_AVAILABLE",
    "TkSettingsWindow",
    "TK_AVAILABLE",
]
