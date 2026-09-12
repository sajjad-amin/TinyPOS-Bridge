from __future__ import annotations
"""
Cross-Platform Settings & Control Panel GUI for TinyPOS Client.
Supports native PyQt6 (primary for Linux/Windows) and Tkinter (fallback).
No browser fallback - fully native desktop GUI only.
"""

import asyncio
import json
import logging
import sys
import threading
import urllib.parse
from typing import Any, Callable, Dict, Optional

from .config import config, get_default_client_name
from .ble_driver import ble_driver
from .relay_worker import relay_worker

logger = logging.getLogger("tinypos.client.settings")

# 1. Check for PyQt6 (preferred modern GUI toolkit)
PYQT_AVAILABLE = False
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    PYQT_AVAILABLE = True
except (ImportError, ModuleNotFoundError, Exception):
    PYQT_AVAILABLE = False

# 2. Check for Tkinter (secondary fallback)
TK_AVAILABLE = False
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    TK_AVAILABLE = True
except (ImportError, ModuleNotFoundError, Exception):
    tk = None
    ttk = None
    messagebox = None
    TK_AVAILABLE = False


def detect_system_dark_theme() -> bool:
    """Detect whether the host OS is using a dark theme (cross-platform)."""
    # 1. PyQt6 / Qt StyleHints check (supports macOS, Windows 10/11, and modern Linux via Freedesktop XDG portal)
    try:
        if PYQT_AVAILABLE:
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
        if PYQT_AVAILABLE:
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


def get_qt_dialog_stylesheet(dark: bool) -> str:
    tokens = {
        "bg_dialog": "#0f172a" if dark else "#f8fafc",
        "bg_card": "#1e293b" if dark else "#ffffff",
        "border_card": "#334155" if dark else "#e2e8f0",
        "text_title": "#f8fafc" if dark else "#0f172a",
        "text_body": "#cbd5e1" if dark else "#334155",
        "text_muted": "#94a3b8" if dark else "#64748b",
        "bg_input": "#0f172a" if dark else "#ffffff",
        "border_input": "#475569" if dark else "#cbd5e1",
        "text_input": "#f8fafc" if dark else "#0f172a",
        "bg_btn": "#1e293b" if dark else "#f1f5f9",
        "border_btn": "#475569" if dark else "#cbd5e1",
        "text_btn": "#f8fafc" if dark else "#1e293b",
        "bg_btn_hover": "#334155" if dark else "#e2e8f0",
        "border_btn_hover": "#64748b" if dark else "#94a3b8",
        "bg_btn_paste": "#1e1b4b" if dark else "#e0e7ff",
        "border_btn_paste": "#4338ca" if dark else "#c7d2fe",
        "text_btn_paste": "#c7d2fe" if dark else "#3730a3",
        "bg_btn_paste_hover": "#312e81" if dark else "#c7d2fe",
        "bg_btn_save": "#059669" if dark else "#10b981",
        "border_btn_save": "#10b981" if dark else "#059669",
        "bg_btn_save_hover": "#10b981" if dark else "#059669",
        "bg_btn_remove": "#450a0a" if dark else "#fee2e2",
        "border_btn_remove": "#7f1d1d" if dark else "#fca5a5",
        "text_btn_remove": "#fca5a5" if dark else "#b91c1c",
        "bg_btn_remove_hover": "#5c1313" if dark else "#fecaca",
        "scrollbar_handle": "#475569" if dark else "#cbd5e1",
        "scrollbar_hover": "#64748b" if dark else "#94a3b8",
    }
    return """
        QDialog {
            background-color: %(bg_dialog)s;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Ubuntu, Cantarell, sans-serif;
        }
        QScrollArea {
            background-color: transparent;
            border: none;
        }
        QWidget#scrollContent {
            background-color: transparent;
        }
        QGroupBox {
            background-color: %(bg_card)s;
            border: 1px solid %(border_card)s;
            border-radius: 8px;
            margin-top: 14px;
            padding: 12px 14px 14px 14px;
            font-weight: bold;
            color: %(text_title)s;
            font-size: 13px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: %(text_title)s;
            background-color: %(bg_card)s;
            border-radius: 3px;
        }
        QLabel {
            color: %(text_body)s;
            font-size: 13px;
        }
        QLabel#lblHeaderTitle {
            font-size: 18px;
            font-weight: bold;
            color: %(text_title)s;
        }
        QLabel#lblHeaderSub {
            font-size: 12px;
            color: %(text_muted)s;
        }
        QLabel#lblQuickDesc {
            font-size: 11px;
            color: %(text_muted)s;
        }
        QLineEdit {
            background-color: %(bg_input)s;
            border: 1px solid %(border_input)s;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
            color: %(text_input)s;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            min-height: 24px;
            max-height: 24px;
        }
        QLineEdit:focus {
            border: 1.5px solid #3b82f6;
        }
        QComboBox {
            background-color: %(bg_input)s;
            border: 1px solid %(border_input)s;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
            color: %(text_input)s;
            min-height: 24px;
            max-height: 24px;
        }
        QComboBox:focus {
            border: 1.5px solid #3b82f6;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: none;
        }
        QComboBox QAbstractItemView {
            background-color: %(bg_card)s;
            border: 1px solid %(border_card)s;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            color: %(text_input)s;
            padding: 4px;
        }
        QPushButton {
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid %(border_btn)s;
            background-color: %(bg_btn)s;
            color: %(text_btn)s;
            min-height: 24px;
            max-height: 24px;
        }
        QPushButton:hover {
            background-color: %(bg_btn_hover)s;
            border-color: %(border_btn_hover)s;
        }
        QPushButton#btnPaste {
            background-color: %(bg_btn_paste)s;
            border: 1px solid %(border_btn_paste)s;
            color: %(text_btn_paste)s;
        }
        QPushButton#btnPaste:hover {
            background-color: %(bg_btn_paste_hover)s;
        }
        QPushButton#btnSave {
            background-color: %(bg_btn_save)s;
            border: 1px solid %(border_btn_save)s;
            color: #ffffff;
        }
        QPushButton#btnSave:hover {
            background-color: %(bg_btn_save_hover)s;
        }
        QPushButton#btnRemove {
            background-color: %(bg_btn_remove)s;
            border: 1px solid %(border_btn_remove)s;
            color: %(text_btn_remove)s;
        }
        QPushButton#btnRemove:hover {
            background-color: %(bg_btn_remove_hover)s;
        }
        QScrollBar:vertical {
            border: none;
            background-color: transparent;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background-color: %(scrollbar_handle)s;
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: %(scrollbar_hover)s;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        QMessageBox {
            background-color: %(bg_dialog)s;
        }
        QMessageBox QLabel {
            color: %(text_title)s;
        }
    """ % tokens


if PYQT_AVAILABLE:
    class QtSettingsDialog(QtWidgets.QDialog):
        """Native modern PyQt6 Settings and Control Panel Dialog."""

        def __init__(self, parent=None, on_save_callback: Optional[Callable[[], None]] = None):
            super().__init__(parent)
            self.on_save_callback = on_save_callback
            self._show_key = False
            self._is_dark = detect_system_dark_theme()
            self.setWindowTitle("TinyPOS - Control Panel & Settings")
            self.resize(560, 710)
            self.setMinimumSize(480, 520)
            self.init_ui()

            # Listen to system color scheme changes (Qt 6.5+)
            try:
                hints = QtGui.QGuiApplication.styleHints()
                if hasattr(hints, "colorSchemeChanged"):
                    hints.colorSchemeChanged.connect(self._on_color_scheme_changed)
            except Exception:
                pass

        def showEvent(self, event: QtGui.QShowEvent):
            super().showEvent(event)
            current_dark = detect_system_dark_theme()
            if current_dark != self._is_dark:
                self._is_dark = current_dark
                self.apply_theme()
            if hasattr(self, "combo_printer"):
                self._populate_printer_combo()

        def _on_color_scheme_changed(self):
            self._is_dark = detect_system_dark_theme()
            self.apply_theme()

        def apply_theme(self):
            self.setStyleSheet(get_qt_dialog_stylesheet(self._is_dark))
            if hasattr(self, "lbl_relay_status"):
                self.update_status()

        def init_ui(self):
            self.apply_theme()

            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(18, 16, 18, 16)
            root_layout.setSpacing(10)

            # 1. Header
            header_layout = QtWidgets.QVBoxLayout()
            header_layout.setSpacing(3)
            self.lbl_title = QtWidgets.QLabel("TinyPOS Cloud Bridge")
            self.lbl_title.setObjectName("lblHeaderTitle")
            self.lbl_sub = QtWidgets.QLabel("Connect your portable Bluetooth thermal printer to the TinyPOS Cloud.")
            self.lbl_sub.setObjectName("lblHeaderSub")
            header_layout.addWidget(self.lbl_title)
            header_layout.addWidget(self.lbl_sub)
            root_layout.addLayout(header_layout)

            # 2. Scroll Area for Content (prevents layout squishing regardless of screen size)
            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

            content_widget = QtWidgets.QWidget()
            content_widget.setObjectName("scrollContent")
            content_layout = QtWidgets.QVBoxLayout(content_widget)
            content_layout.setContentsMargins(2, 4, 2, 4)
            content_layout.setSpacing(12)

            # 2. Live Status Banner
            status_box = QtWidgets.QGroupBox("Live Hardware && Cloud Status")
            status_layout = QtWidgets.QVBoxLayout(status_box)
            status_layout.setSpacing(6)

            self.lbl_relay_status = QtWidgets.QLabel("Cloud Relay: Connecting...")
            self.lbl_group = QtWidgets.QLabel("API Group: --")
            self.lbl_printer = QtWidgets.QLabel("Printer: Scanning Bluetooth...")
            status_layout.addWidget(self.lbl_relay_status)
            status_layout.addWidget(self.lbl_group)
            status_layout.addWidget(self.lbl_printer)

            # Quick action buttons inside status banner
            act_bar = QtWidgets.QHBoxLayout()
            act_bar.setSpacing(8)
            btn_feed = QtWidgets.QPushButton("📄 Feed Paper")
            btn_feed.clicked.connect(self._on_feed_paper)
            btn_reconnect = QtWidgets.QPushButton("🔄 Reconnect Now")
            btn_reconnect.clicked.connect(self._on_reconnect_now)
            act_bar.addWidget(btn_feed)
            act_bar.addWidget(btn_reconnect)
            act_bar.addStretch()
            status_layout.addLayout(act_bar)
            content_layout.addWidget(status_box)

            # 3. Quick Connect (Copy-Paste)
            quick_box = QtWidgets.QGroupBox("Quick Connect (Paste from Web Console)")
            quick_layout = QtWidgets.QVBoxLayout(quick_box)
            quick_layout.setSpacing(6)

            quick_desc = QtWidgets.QLabel("Copy the Client WebSocket URL from your TinyPOS web dashboard and paste it here:")
            quick_desc.setObjectName("lblQuickDesc")
            quick_layout.addWidget(quick_desc)

            quick_input_row = QtWidgets.QHBoxLayout()
            quick_input_row.setSpacing(8)
            self.input_quick = QtWidgets.QLineEdit()
            self.input_quick.setPlaceholderText("wss://pos.sayem.top/ws/client?api_key=...")
            btn_paste = QtWidgets.QPushButton("📋 Paste && Apply")
            btn_paste.setObjectName("btnPaste")
            btn_paste.setFixedWidth(130)
            btn_paste.clicked.connect(self._on_paste_quick)
            quick_input_row.addWidget(self.input_quick)
            quick_input_row.addWidget(btn_paste)
            quick_layout.addLayout(quick_input_row)
            content_layout.addWidget(quick_box)

            # 4. Connection Details
            details_box = QtWidgets.QGroupBox("Server && Terminal Configuration")
            details_layout = QtWidgets.QVBoxLayout(details_box)
            details_layout.setSpacing(6)

            details_layout.addWidget(QtWidgets.QLabel("Cloud Relay URL (e.g. wss://pos.sayem.top):"))
            self.input_server = QtWidgets.QLineEdit(config.server_url or "wss://pos.sayem.top")
            details_layout.addWidget(self.input_server)

            details_layout.addWidget(QtWidgets.QLabel("Client API Key (sk_client_...):"))
            key_row = QtWidgets.QHBoxLayout()
            key_row.setSpacing(8)
            self.input_key = QtWidgets.QLineEdit(config.client_api_key)
            self.input_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self.btn_toggle_key = QtWidgets.QPushButton("👁 Show")
            self.btn_toggle_key.setFixedWidth(80)
            self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
            key_row.addWidget(self.input_key)
            key_row.addWidget(self.btn_toggle_key)
            details_layout.addLayout(key_row)

            details_layout.addWidget(QtWidgets.QLabel("Terminal / Station Identifier:"))
            self.input_name = QtWidgets.QLineEdit(config.client_name or get_default_client_name())
            details_layout.addWidget(self.input_name)
            content_layout.addWidget(details_box)

            # 5. Target Bluetooth Thermal Printer
            printer_box = QtWidgets.QGroupBox("Target Bluetooth Thermal Printer")
            printer_layout = QtWidgets.QVBoxLayout(printer_box)
            printer_layout.setSpacing(6)

            printer_desc = QtWidgets.QLabel("Select a specific printer or let TinyPOS auto-connect to the nearest one:")
            printer_desc.setObjectName("lblQuickDesc")
            printer_layout.addWidget(printer_desc)

            printer_row = QtWidgets.QHBoxLayout()
            printer_row.setSpacing(8)

            self.combo_printer = QtWidgets.QComboBox()
            self.combo_printer.setFixedHeight(38)
            self._populate_printer_combo()

            self.btn_scan_printers = QtWidgets.QPushButton("🔍 Scan")
            self.btn_scan_printers.setFixedSize(90, 38)
            self.btn_scan_printers.clicked.connect(self._on_scan_printers)

            printer_row.addWidget(self.combo_printer, 1)
            printer_row.addWidget(self.btn_scan_printers)
            printer_layout.addLayout(printer_row)

            self.lbl_printer_hint = QtWidgets.QLabel("💡 Fallback Mode: If the selected printer is offline, TinyPOS auto-connects to the closest printer.")
            self.lbl_printer_hint.setObjectName("lblQuickDesc")
            self.lbl_printer_hint.setWordWrap(True)
            printer_layout.addWidget(self.lbl_printer_hint)

            content_layout.addWidget(printer_box)

            # 6. Live Test Status Label
            self.lbl_test_result = QtWidgets.QLabel("")
            self.lbl_test_result.setWordWrap(True)
            self.lbl_test_result.setMinimumHeight(24)
            content_layout.addWidget(self.lbl_test_result)

            scroll_area.setWidget(content_widget)
            root_layout.addWidget(scroll_area, 1)

            # 7. Bottom Action Bar (pinned)
            btn_bar = QtWidgets.QHBoxLayout()
            btn_bar.setSpacing(8)

            self.btn_test = QtWidgets.QPushButton("🧪 Test Connection")
            self.btn_test.clicked.connect(self._on_test_connection)
            btn_bar.addWidget(self.btn_test)

            btn_remove = QtWidgets.QPushButton("🗑️ Remove Config")
            btn_remove.setObjectName("btnRemove")
            btn_remove.clicked.connect(self._on_remove_config)
            btn_bar.addWidget(btn_remove)

            btn_bar.addStretch()

            btn_close = QtWidgets.QPushButton("Close")
            btn_close.setFixedWidth(80)
            btn_close.clicked.connect(self.hide)
            btn_bar.addWidget(btn_close)

            btn_save = QtWidgets.QPushButton("💾 Save && Connect")
            btn_save.setObjectName("btnSave")
            btn_save.clicked.connect(self._on_save)
            btn_bar.addWidget(btn_save)

            root_layout.addLayout(btn_bar)

            # Initial status update
            self.update_status()

        def _populate_printer_combo(self, discovered_list=None):
            """Populate the printer selection dropdown with discovered and saved printers."""
            self.combo_printer.clear()
            self.combo_printer.addItem("⚡ Auto: Closest Printer (Strongest Signal)", "")

            seen = set()
            saved_addr = (config.printer_address or "").strip()
            if saved_addr:
                label = f"🖨️ {config.printer_name or 'Saved Printer'} ({saved_addr}) [Selected]"
                self.combo_printer.addItem(label, saved_addr)
                seen.add(saved_addr.lower())

            items = discovered_list if discovered_list is not None else ble_driver.discovered_printers
            for p in items:
                addr = (p.get("address") or "").strip()
                if not addr or addr.lower() in seen:
                    continue
                seen.add(addr.lower())
                rssi_str = f" [{p['rssi']} dBm]" if p.get("rssi") is not None else ""
                self.combo_printer.addItem(f"🖨️ {p.get('name', 'Printer')} ({addr}){rssi_str}", addr)

            if saved_addr:
                idx = -1
                for i in range(self.combo_printer.count()):
                    d = str(self.combo_printer.itemData(i) or "").strip()
                    if d.lower() == saved_addr.lower():
                        idx = i
                        break
                if idx >= 0:
                    self.combo_printer.setCurrentIndex(idx)
                else:
                    self.combo_printer.setCurrentIndex(0)
            else:
                self.combo_printer.setCurrentIndex(0)

        def _on_scan_printers(self):
            """Scan for nearby thermal printers asynchronously and update dropdown."""
            self.btn_scan_printers.setEnabled(False)
            self.btn_scan_printers.setText("⏳ Scanning...")

            def _scan():
                printers = asyncio.run(ble_driver.discover_printers(timeout=4.0))

                def _update():
                    self.btn_scan_printers.setEnabled(True)
                    self.btn_scan_printers.setText("🔍 Scan")
                    self._populate_printer_combo(printers)
                    count = len(printers)
                    msg = f"Found {count} printer{'s' if count != 1 else ''} nearby."
                    self.lbl_printer_hint.setText(f"✅ Scan complete! {msg} Fallback mode active if unselected.")

                QtCore.QMetaObject.invokeMethod(self, "_exec_callback", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(object, _update))

            threading.Thread(target=_scan, daemon=True).start()

        def update_status(self, extra: Optional[Dict[str, Any]] = None):
            """Update live status display."""
            dark = self._is_dark
            neutral_col = "#94a3b8" if dark else "#64748b"
            green_col = "#22c55e" if dark else "#16a34a"
            amber_col = "#f59e0b" if dark else "#d97706"
            red_col = "#ef4444" if dark else "#dc2626"

            if not config.is_configured():
                self.lbl_relay_status.setText("Cloud Relay: ⚪ Not Configured")
                self.lbl_relay_status.setStyleSheet(f"color: {neutral_col}; font-weight: bold;")
                self.lbl_group.setText("API Group: --")
                self.lbl_printer.setText("Printer: Configure server and key below")
                return

            if relay_worker.is_connected:
                group = relay_worker.current_group or "Pending..."
                self.lbl_relay_status.setText(f"Cloud Relay: 🟢 Connected ({config.server_url})")
                self.lbl_relay_status.setStyleSheet(f"color: {green_col}; font-weight: bold;")
                self.lbl_group.setText(f"API Group: {group}")

                if ble_driver.is_online:
                    rssi_str = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                    self.lbl_printer.setText(f"Printer: 🖨️ {ble_driver.device_name}{rssi_str} (Online)")
                    self.lbl_printer.setStyleSheet(f"color: {green_col};")
                else:
                    self.lbl_printer.setText("Printer: 🟡 Scanning / Printer Offline")
                    self.lbl_printer.setStyleSheet(f"color: {amber_col};")
            else:
                msg = relay_worker.last_status_message or "Connecting..."
                self.lbl_relay_status.setText(f"Cloud Relay: 🔴 {msg}")
                self.lbl_relay_status.setStyleSheet(f"color: {red_col}; font-weight: bold;")
                self.lbl_group.setText("API Group: --")
                if ble_driver.is_online:
                    self.lbl_printer.setText(f"Printer: 🖨️ {ble_driver.device_name} (Bluetooth Ready)")
                    self.lbl_printer.setStyleSheet(f"color: {green_col};")
                else:
                    self.lbl_printer.setText("Printer: ⚪ Offline")
                    self.lbl_printer.setStyleSheet(f"color: {neutral_col};")

        def _toggle_key_visibility(self):
            self._show_key = not self._show_key
            if self._show_key:
                self.input_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
                self.btn_toggle_key.setText("🙈 Hide")
            else:
                self.input_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
                self.btn_toggle_key.setText("👁 Show")

        def _on_paste_quick(self):
            cb = QtWidgets.QApplication.clipboard()
            pasted = (cb.text() or "").strip()
            if not pasted:
                pasted = self.input_quick.text().strip()

            if not pasted:
                QtWidgets.QMessageBox.information(self, "Clipboard Empty", "Please copy your WebSocket connection URL from the web console first.")
                return

            self.input_quick.setText(pasted)
            parsed = config.parse_ws_url(pasted)

            green_col = "#22c55e" if self._is_dark else "#16a34a"
            amber_col = "#f59e0b" if self._is_dark else "#d97706"

            if parsed and parsed.get("client_api_key"):
                if parsed.get("server_url"):
                    self.input_server.setText(parsed["server_url"])
                if parsed.get("client_api_key"):
                    self.input_key.setText(parsed["client_api_key"])
                if parsed.get("client_name"):
                    self.input_name.setText(parsed["client_name"])
                self.lbl_test_result.setStyleSheet(f"color: {green_col}; font-weight: bold;")
                self.lbl_test_result.setText("✅ Auto-filled credentials from WebSocket URL!")
            elif pasted.startswith("sk_client_"):
                self.input_key.setText(pasted)
                self.lbl_test_result.setStyleSheet(f"color: {green_col}; font-weight: bold;")
                self.lbl_test_result.setText("✅ Auto-filled Client API Key!")
            else:
                self.lbl_test_result.setStyleSheet(f"color: {amber_col};")
                self.lbl_test_result.setText("⚠️ Could not extract credentials. Please fill manually.")

        def _on_feed_paper(self):
            relay_worker.feed_paper()

        def _on_reconnect_now(self):
            relay_worker.trigger_reconnect()

        def _on_test_connection(self):
            server_url = self.input_server.text().strip()
            api_key = self.input_key.text().strip()
            client_name = self.input_name.text().strip() or get_default_client_name()

            red_col = "#ef4444" if self._is_dark else "#dc2626"
            blue_col = "#60a5fa" if self._is_dark else "#2563eb"
            green_col = "#22c55e" if self._is_dark else "#16a34a"

            if not server_url or not api_key:
                self.lbl_test_result.setStyleSheet(f"color: {red_col}; font-weight: bold;")
                self.lbl_test_result.setText("❌ Please enter both Server URL and Client API Key.")
                return

            self.btn_test.setEnabled(False)
            self.lbl_test_result.setStyleSheet(f"color: {blue_col};")
            self.lbl_test_result.setText("⏳ Connecting to WebSocket relay...")

            def _test():
                import websockets

                async def _connect():
                    parsed = urllib.parse.urlparse(server_url)
                    scheme = "wss" if parsed.scheme.lower() in ("https", "wss") else "ws"
                    netloc = parsed.netloc or parsed.path.split("/")[0]
                    query = urllib.parse.urlencode({"api_key": api_key, "client_name": client_name})
                    ws_url = f"{scheme}://{netloc}/ws/client?{query}"

                    try:
                        async with websockets.connect(ws_url, open_timeout=6.0, close_timeout=2.0) as ws:
                            raw = await asyncio.wait_for(ws.recv(), timeout=4.0)
                            data = json.loads(raw)
                            group = data.get("group") or "Default"
                            return True, f"✅ Connected successfully! Authorized for Group: '{group}'"
                    except asyncio.TimeoutError:
                        return False, "❌ Connection timed out after 6 seconds."
                    except websockets.InvalidStatusCode as e:
                        if e.status_code == 403:
                            return False, "❌ Unauthorized: Invalid or inactive Client API Key (HTTP 403)."
                        return False, f"❌ Server returned HTTP error {e.status_code}."
                    except Exception as e:
                        return False, f"❌ Connection failed: {e}"

                success, message = asyncio.run(_connect())

                def _update():
                    self.btn_test.setEnabled(True)
                    col = green_col if success else red_col
                    self.lbl_test_result.setStyleSheet(f"color: {col}; font-weight: bold;")
                    self.lbl_test_result.setText(message)

                QtCore.QMetaObject.invokeMethod(self, "_exec_callback", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(object, _update))

            threading.Thread(target=_test, daemon=True).start()

        @QtCore.pyqtSlot(object)
        def _exec_callback(self, func):
            func()

        def _on_remove_config(self):
            """Confirm and delete saved client configuration."""
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Remove Configuration?",
                "Are you sure you want to remove the saved Server URL and API Key from this machine?\n\nThis will disconnect from the cloud relay.",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )

            if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
                config.delete()
                ble_driver.reset_cache()
                self.input_server.setText("")
                self.input_key.setText("")
                self.input_name.setText(config.client_name)
                self.input_quick.setText("")
                if hasattr(self, "combo_printer"):
                    self.combo_printer.setCurrentIndex(0)
                amber_col = "#f59e0b" if self._is_dark else "#d97706"
                self.lbl_test_result.setStyleSheet(f"color: {amber_col}; font-weight: bold;")
                self.lbl_test_result.setText("⚪ Configuration removed. Client disconnected.")
                self.update_status()
                relay_worker.trigger_reconnect()
                if self.on_save_callback:
                    self.on_save_callback()

        def _on_save(self):
            server = self.input_server.text().strip()
            key = self.input_key.text().strip()
            name = self.input_name.text().strip() or get_default_client_name()

            if not server or not key:
                QtWidgets.QMessageBox.warning(self, "Incomplete Settings", "Please enter both the Cloud Relay URL and your Client API Key.")
                return

            config.server_url = server
            config.client_api_key = key
            config.client_name = name

            if hasattr(self, "combo_printer"):
                selected_addr = (self.combo_printer.currentData() or "").strip()
                selected_text = self.combo_printer.currentText()
                if not selected_addr:
                    config.printer_address = ""
                    config.printer_name = ""
                else:
                    config.printer_address = selected_addr
                    clean_name = selected_text.replace("🖨️", "").split("(")[0].strip()
                    config.printer_name = clean_name

            config.save()
            ble_driver.reset_cache()

            self.hide()
            relay_worker.trigger_reconnect()

            if self.on_save_callback:
                self.on_save_callback()


elif TK_AVAILABLE:
    class TkSettingsWindow:
        """Tkinter-based fallback Settings and Control Panel Dialog."""

        def __init__(self, on_save_callback: Optional[Callable[[], None]] = None):
            self.on_save_callback = on_save_callback
            self.root: Optional[Any] = None
            self._is_visible = False
            self._show_key = False

            self.ws_quick_var = None
            self.server_url_var = None
            self.api_key_var = None
            self.client_name_var = None

            self.lbl_relay_status = None
            self.lbl_group = None
            self.lbl_printer = None
            self.lbl_test_result = None
            self.btn_test = None
            self.btn_show_key = None
            self.entry_api_key = None

        def init_ui(self, root: Any):
            self.root = root
            self.root.title("TinyPOS - Control Panel & Settings")
            self.root.geometry("560x730")
            self.root.minsize(520, 600)
            is_dark = detect_system_dark_theme()
            self._is_dark = is_dark

            bg = "#0f172a" if is_dark else "#f8fafc"
            card_bg = "#1e293b" if is_dark else "#ffffff"
            card_fg = "#f8fafc" if is_dark else "#1e293b"
            fg_title = "#f8fafc" if is_dark else "#0f172a"
            fg_muted = "#94a3b8" if is_dark else "#64748b"
            fg_label = "#cbd5e1" if is_dark else "#334155"
            entry_bg = "#0f172a" if is_dark else "#ffffff"
            entry_fg = "#f8fafc" if is_dark else "#0f172a"
            btn_bg = "#334155" if is_dark else "#f1f5f9"
            btn_fg = "#f8fafc" if is_dark else "#1e293b"

            self.root.configure(bg=bg)
            self.root.protocol("WM_DELETE_WINDOW", self.hide)

            container = tk.Frame(self.root, bg=bg, padx=24, pady=20)
            container.pack(fill="both", expand=True)

            # Header
            header_frame = tk.Frame(container, bg=bg)
            header_frame.pack(fill="x", pady=(0, 14))
            tk.Label(
                header_frame, text="TinyPOS Cloud Bridge",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 16, "bold"),
                bg=bg, fg=fg_title
            ).pack(anchor="w")
            tk.Label(
                header_frame, text="Connect your portable Bluetooth thermal printer to the TinyPOS Cloud.",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg=bg, fg=fg_muted
            ).pack(anchor="w", pady=(2, 0))

            # Status Banner
            status_card = tk.LabelFrame(
                container, text=" Live Hardware & Cloud Status ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg=card_bg, fg=card_fg, padx=14, pady=10, relief="solid", bd=1
            )
            status_card.pack(fill="x", pady=(0, 14))

            self.lbl_relay_status = tk.Label(status_card, text="Cloud Relay: Connecting...", bg=card_bg, fg=fg_label)
            self.lbl_relay_status.pack(anchor="w", pady=1)
            self.lbl_group = tk.Label(status_card, text="API Group: --", bg=card_bg, fg=fg_muted)
            self.lbl_group.pack(anchor="w", pady=1)
            self.lbl_printer = tk.Label(status_card, text="Printer: Scanning Bluetooth...", bg=card_bg, fg=fg_label)
            self.lbl_printer.pack(anchor="w", pady=1)

            action_bar = tk.Frame(status_card, bg=card_bg)
            action_bar.pack(anchor="w", pady=(6, 2))
            tk.Button(action_bar, text="📄 Feed Paper", command=self._on_feed_paper, bg=btn_bg, fg=btn_fg, padx=8, pady=4).pack(side="left", padx=(0, 8))
            tk.Button(action_bar, text="🔄 Reconnect Now", command=self._on_reconnect_now, bg=btn_bg, fg=btn_fg, padx=8, pady=4).pack(side="left")

            # Quick Connect
            quick_card = tk.LabelFrame(
                container, text=" Quick Connect (Paste from Web Console) ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg=card_bg, fg=card_fg, padx=14, pady=10, relief="solid", bd=1
            )
            quick_card.pack(fill="x", pady=(0, 14))
            tk.Label(quick_card, text="Paste the Client WebSocket URL from your web console:", bg=card_bg, fg=fg_muted, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

            quick_row = tk.Frame(quick_card, bg=card_bg)
            quick_row.pack(fill="x")
            self.ws_quick_var = tk.StringVar()
            tk.Entry(quick_row, textvariable=self.ws_quick_var, bg=entry_bg, fg=entry_fg, insertbackground=entry_fg).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
            tk.Button(quick_row, text="📋 Paste & Apply", command=self._on_paste_quick, bg="#1e1b4b" if is_dark else "#e0e7ff", fg="#c7d2fe" if is_dark else "#3730a3").pack(side="right")

            # Details
            details_card = tk.LabelFrame(
                container, text=" Server & Terminal Configuration ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg=card_bg, fg=card_fg, padx=14, pady=10, relief="solid", bd=1
            )
            details_card.pack(fill="x", pady=(0, 14))

            tk.Label(details_card, text="Cloud Relay URL:", bg=card_bg, fg=fg_label).pack(anchor="w")
            self.server_url_var = tk.StringVar(value=config.server_url or "wss://pos.sayem.top")
            tk.Entry(details_card, textvariable=self.server_url_var, bg=entry_bg, fg=entry_fg, insertbackground=entry_fg).pack(fill="x", ipady=6, pady=(2, 6))

            tk.Label(details_card, text="Client API Key:", bg=card_bg, fg=fg_label).pack(anchor="w")
            key_row = tk.Frame(details_card, bg=card_bg)
            key_row.pack(fill="x", pady=(2, 6))
            self.api_key_var = tk.StringVar(value=config.client_api_key)
            self.entry_api_key = tk.Entry(key_row, textvariable=self.api_key_var, show="*", bg=entry_bg, fg=entry_fg, insertbackground=entry_fg)
            self.entry_api_key.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
            self.btn_show_key = tk.Button(key_row, text="👁 Show", command=self._toggle_show_key, bg=btn_bg, fg=btn_fg, padx=8, pady=4)
            self.btn_show_key.pack(side="right")

            tk.Label(details_card, text="Terminal Identifier:", bg=card_bg, fg=fg_label).pack(anchor="w")
            self.client_name_var = tk.StringVar(value=config.client_name or get_default_client_name())
            tk.Entry(details_card, textvariable=self.client_name_var, bg=entry_bg, fg=entry_fg, insertbackground=entry_fg).pack(fill="x", ipady=6, pady=(2, 4))

            # Target Bluetooth Thermal Printer
            printer_card = tk.LabelFrame(
                container, text=" Target Bluetooth Thermal Printer ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg=card_bg, fg=card_fg, padx=14, pady=10, relief="solid", bd=1
            )
            printer_card.pack(fill="x", pady=(0, 14))

            tk.Label(printer_card, text="Select specific printer or auto-connect to nearest:", bg=card_bg, fg=fg_muted, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

            printer_row = tk.Frame(printer_card, bg=card_bg)
            printer_row.pack(fill="x")

            self.printer_combo_var = tk.StringVar()
            self.printer_addr_map = {}
            self.combo_printer = ttk.Combobox(printer_row, textvariable=self.printer_combo_var, state="readonly")
            self.combo_printer.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

            self.btn_scan_printers = tk.Button(printer_row, text="🔍 Scan", command=self._on_scan_printers, bg=btn_bg, fg=btn_fg, padx=8, pady=4)
            self.btn_scan_printers.pack(side="right")

            self.lbl_printer_hint = tk.Label(printer_card, text="💡 Fallback: If target offline, connects to closest printer.", bg=card_bg, fg=fg_muted, font=("Segoe UI", 8))
            self.lbl_printer_hint.pack(anchor="w", pady=(4, 0))

            self._populate_printer_combo()

            # Test Label
            self.lbl_test_result = tk.Label(container, text="", bg=bg, fg=fg_muted, wraplength=480, justify="left")
            self.lbl_test_result.pack(anchor="w", pady=(0, 6))

            # Bottom Bar
            btn_bar = tk.Frame(container, bg=bg)
            btn_bar.pack(fill="x", pady=(4, 0))

            self.btn_test = tk.Button(btn_bar, text="🧪 Test Connection", command=self._on_test_connection, bg=btn_bg, fg=btn_fg, padx=8, pady=4)
            self.btn_test.pack(side="left")

            btn_remove = tk.Button(btn_bar, text="🗑️ Remove Config", command=self._on_remove_config, bg="#450a0a" if is_dark else "#fee2e2", fg="#fca5a5" if is_dark else "#b91c1c", padx=8, pady=4)
            btn_remove.pack(side="left", padx=(8, 0))

            btn_save = tk.Button(btn_bar, text="💾 Save & Connect", command=self._on_save, bg="#059669" if is_dark else "#10b981", fg="#ffffff", padx=14, pady=4)
            btn_save.pack(side="right", padx=(8, 0))

            btn_close = tk.Button(btn_bar, text="Close", command=self.hide, bg=btn_bg, fg=btn_fg, padx=10, pady=4)
            btn_close.pack(side="right")

            self.update_status()

        def show(self):
            if not self.root:
                return
            self._is_visible = True
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self._populate_printer_combo()
            self.update_status()

        def hide(self):
            if not self.root:
                return
            self._is_visible = False
            self.root.withdraw()

        def update_status(self, extra=None):
            if not self.root or not self.lbl_relay_status:
                return

            def _do():
                dark = getattr(self, "_is_dark", False)
                neutral_col = "#94a3b8" if dark else "#64748b"
                green_col = "#22c55e" if dark else "#16a34a"
                amber_col = "#f59e0b" if dark else "#d97706"
                red_col = "#ef4444" if dark else "#dc2626"
                fg_label = "#cbd5e1" if dark else "#334155"

                if not config.is_configured():
                    self.lbl_relay_status.config(text="Cloud Relay: ⚪ Not Configured", fg=neutral_col)
                    self.lbl_group.config(text="API Group: --", fg=neutral_col)
                    self.lbl_printer.config(text="Printer: Configure server and key above", fg=neutral_col)
                    return
                if relay_worker.is_connected:
                    group = relay_worker.current_group or "Pending..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🟢 Connected ({config.server_url})", fg=green_col)
                    self.lbl_group.config(text=f"API Group: {group}", fg=fg_label)
                    if ble_driver.is_online:
                        rssi = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                        self.lbl_printer.config(text=f"Printer: 🖨️ {ble_driver.device_name}{rssi} (Online)", fg=green_col)
                    else:
                        self.lbl_printer.config(text="Printer: 🟡 Scanning / Printer Offline", fg=amber_col)
                else:
                    msg = relay_worker.last_status_message or "Connecting..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🔴 {msg}", fg=red_col)
                    self.lbl_group.config(text="API Group: --", fg=neutral_col)
                    self.lbl_printer.config(text=f"Printer: {'Online' if ble_driver.is_online else 'Offline'}", fg=neutral_col)

            try:
                self.root.after(0, _do)
            except Exception:
                pass

        def _toggle_show_key(self):
            self._show_key = not self._show_key
            if self._show_key:
                self.entry_api_key.config(show="")
                self.btn_show_key.config(text="🙈 Hide")
            else:
                self.entry_api_key.config(show="*")
                self.btn_show_key.config(text="👁 Show")

        def _on_paste_quick(self):
            try:
                pasted = self.root.clipboard_get().strip()
            except Exception:
                pasted = (self.ws_quick_var.get() if self.ws_quick_var else "").strip()

            if not pasted:
                return

            self.ws_quick_var.set(pasted)
            parsed = config.parse_ws_url(pasted)
            if parsed.get("client_api_key"):
                if parsed.get("server_url"):
                    self.server_url_var.set(parsed["server_url"])
                if parsed.get("client_api_key"):
                    self.api_key_var.set(parsed["client_api_key"])
                if parsed.get("client_name"):
                    self.client_name_var.set(parsed["client_name"])
                self.lbl_test_result.config(text="✅ Auto-filled from URL!", fg="#16a34a")

        def _on_feed_paper(self):
            relay_worker.feed_paper()

        def _on_reconnect_now(self):
            relay_worker.trigger_reconnect()

        def _populate_printer_combo(self, discovered_list=None):
            """Populate the printer dropdown for Tkinter."""
            self.printer_addr_map = {"⚡ Auto: Closest Printer (Strongest Signal)": ""}
            labels = ["⚡ Auto: Closest Printer (Strongest Signal)"]
            seen = set()

            saved_addr = (config.printer_address or "").strip()
            if saved_addr:
                lbl = f"🖨️ {config.printer_name or 'Saved Printer'} ({saved_addr}) [Selected]"
                labels.append(lbl)
                self.printer_addr_map[lbl] = saved_addr
                seen.add(saved_addr.lower())

            items = discovered_list if discovered_list is not None else ble_driver.discovered_printers
            for p in items:
                addr = (p.get("address") or "").strip()
                if not addr or addr.lower() in seen:
                    continue
                seen.add(addr.lower())
                rssi_str = f" [{p['rssi']} dBm]" if p.get("rssi") is not None else ""
                lbl = f"🖨️ {p.get('name', 'Printer')} ({addr}){rssi_str}"
                labels.append(lbl)
                self.printer_addr_map[lbl] = addr

            if hasattr(self, "combo_printer") and self.combo_printer:
                self.combo_printer["values"] = labels
                selected_label = labels[0]
                if saved_addr:
                    for l, a in self.printer_addr_map.items():
                        if a.lower() == saved_addr.lower():
                            selected_label = l
                            break
                self.printer_combo_var.set(selected_label)

        def _on_scan_printers(self):
            """Scan for nearby Bluetooth thermal printers asynchronously."""
            if hasattr(self, "btn_scan_printers") and self.btn_scan_printers:
                self.btn_scan_printers.config(state="disabled", text="⏳ Scanning...")

            def _scan():
                printers = asyncio.run(ble_driver.discover_printers(timeout=4.0))

                def _update():
                    if hasattr(self, "btn_scan_printers") and self.btn_scan_printers:
                        self.btn_scan_printers.config(state="normal", text="🔍 Scan")
                    self._populate_printer_combo(printers)
                    count = len(printers)
                    msg = f"Found {count} printer{'s' if count != 1 else ''} nearby."
                    if hasattr(self, "lbl_printer_hint") and self.lbl_printer_hint:
                        self.lbl_printer_hint.config(text=f"✅ Scan complete! {msg} Fallback active.")

                if self.root:
                    self.root.after(0, _update)

            threading.Thread(target=_scan, daemon=True).start()

        def _on_remove_config(self):
            if messagebox.askyesno("Remove Configuration", "Are you sure you want to delete your stored server credentials and disconnect?"):
                config.delete()
                ble_driver.reset_cache()
                self.server_url_var.set("")
                self.api_key_var.set("")
                self.client_name_var.set(config.client_name)
                self.ws_quick_var.set("")
                if hasattr(self, "printer_combo_var") and self.printer_combo_var:
                    self.printer_combo_var.set("⚡ Auto: Closest Printer (Strongest Signal)")
                self.lbl_test_result.config(text="⚪ Configuration removed. Disconnected.", fg="#d97706")
                self.update_status()
                relay_worker.trigger_reconnect()
                if self.on_save_callback:
                    self.on_save_callback()

        def _on_test_connection(self):
            server_url = (self.server_url_var.get() if self.server_url_var else "").strip()
            api_key = (self.api_key_var.get() if self.api_key_var else "").strip()
            client_name = (self.client_name_var.get() if self.client_name_var else "").strip() or get_default_client_name()

            if not server_url or not api_key:
                self.lbl_test_result.config(text="❌ Please enter both Server URL and API Key.", fg="#dc2626")
                return

            self.btn_test.config(state="disabled")
            self.lbl_test_result.config(text="⏳ Connecting to WebSocket relay...", fg="#2563eb")

            def _worker():
                import websockets

                async def _connect():
                    parsed = urllib.parse.urlparse(server_url)
                    scheme = "wss" if parsed.scheme.lower() in ("https", "wss") else "ws"
                    netloc = parsed.netloc or parsed.path.split("/")[0]
                    query = urllib.parse.urlencode({"api_key": api_key, "client_name": client_name})
                    ws_url = f"{scheme}://{netloc}/ws/client?{query}"

                    try:
                        async with websockets.connect(ws_url, open_timeout=6.0, close_timeout=2.0) as ws:
                            raw = await asyncio.wait_for(ws.recv(), timeout=4.0)
                            data = json.loads(raw)
                            group = data.get("group") or "Default"
                            return True, f"✅ Connected successfully! Group: '{group}'"
                    except Exception as e:
                        return False, f"❌ Connection failed: {e}"

                success, message = asyncio.run(_connect())

                def _update():
                    if self.btn_test:
                        self.btn_test.config(state="normal")
                    if self.lbl_test_result:
                        col = "#16a34a" if success else "#dc2626"
                        self.lbl_test_result.config(text=message, fg=col)

                if self.root:
                    self.root.after(0, _update)

            threading.Thread(target=_worker, daemon=True).start()

        def _on_save(self):
            server = (self.server_url_var.get() if self.server_url_var else "").strip()
            key = (self.api_key_var.get() if self.api_key_var else "").strip()
            name = (self.client_name_var.get() if self.client_name_var else "").strip() or get_default_client_name()

            if not server or not key:
                messagebox.showwarning("Incomplete Settings", "Please enter both the Cloud Relay URL and your Client API Key.")
                return

            config.server_url = server
            config.client_api_key = key
            config.client_name = name

            if hasattr(self, "combo_printer") and self.combo_printer and hasattr(self, "printer_addr_map"):
                selected_lbl = self.printer_combo_var.get() if self.printer_combo_var else ""
                selected_addr = self.printer_addr_map.get(selected_lbl, "").strip()
                if not selected_addr:
                    config.printer_address = ""
                    config.printer_name = ""
                else:
                    config.printer_address = selected_addr
                    clean_name = selected_lbl.replace("🖨️", "").split("(")[0].strip()
                    config.printer_name = clean_name

            config.save()
            ble_driver.reset_cache()
            self.hide()
            relay_worker.trigger_reconnect()
            if self.on_save_callback:
                self.on_save_callback()

else:
    # Neither PyQt6 nor Tkinter is installed
    class QtSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            logger.error("No GUI toolkit available to display settings window.")
        def hide(self):
            pass
        def update_status(self, *args, **kwargs):
            pass
