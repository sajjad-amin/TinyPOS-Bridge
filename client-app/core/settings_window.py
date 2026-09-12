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


if PYQT_AVAILABLE:
    class QtSettingsDialog(QtWidgets.QDialog):
        """Native modern PyQt6 Settings and Control Panel Dialog."""

        def __init__(self, parent=None, on_save_callback: Optional[Callable[[], None]] = None):
            super().__init__(parent)
            self.on_save_callback = on_save_callback
            self._show_key = False
            self.setWindowTitle("TinyPOS - Control Panel & Settings")
            self.resize(540, 620)
            self.setMinimumSize(500, 560)
            self.init_ui()

        def init_ui(self):
            self.setStyleSheet("""
                QDialog {
                    background-color: #f8fafc;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                QGroupBox {
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    margin-top: 18px;
                    padding: 14px;
                    font-weight: bold;
                    color: #1e293b;
                    font-size: 13px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 12px;
                    padding: 0 4px;
                }
                QLabel {
                    color: #334155;
                    font-size: 13px;
                }
                QLineEdit {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 13px;
                    color: #0f172a;
                }
                QLineEdit:focus {
                    border-color: #2563eb;
                }
                QPushButton {
                    border-radius: 6px;
                    padding: 7px 14px;
                    font-size: 13px;
                    font-weight: 600;
                    border: 1px solid #cbd5e1;
                    background-color: #f1f5f9;
                    color: #1e293b;
                }
                QPushButton:hover {
                    background-color: #e2e8f0;
                }
                QPushButton#btnSave {
                    background-color: #10b981;
                    border: none;
                    color: #ffffff;
                }
                QPushButton#btnSave:hover {
                    background-color: #059669;
                }
                QPushButton#btnRemove {
                    background-color: #fee2e2;
                    border: 1px solid #fca5a5;
                    color: #b91c1c;
                }
                QPushButton#btnRemove:hover {
                    background-color: #fecaca;
                }
            """)

            main_layout = QtWidgets.QVBoxLayout(self)
            main_layout.setContentsMargins(20, 20, 20, 20)
            main_layout.setSpacing(14)

            # 1. Header
            header_layout = QtWidgets.QVBoxLayout()
            header_layout.setSpacing(3)
            title_lbl = QtWidgets.QLabel("TinyPOS Cloud Bridge")
            title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
            sub_lbl = QtWidgets.QLabel("Connect your portable Bluetooth thermal printer to the TinyPOS Cloud.")
            sub_lbl.setStyleSheet("font-size: 12px; color: #64748b;")
            header_layout.addWidget(title_lbl)
            header_layout.addWidget(sub_lbl)
            main_layout.addLayout(header_layout)

            # 2. Live Status Banner
            status_box = QtWidgets.QGroupBox("Live Hardware & Cloud Status")
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
            main_layout.addWidget(status_box)

            # 3. Quick Connect (Copy-Paste)
            quick_box = QtWidgets.QGroupBox("Quick Connect (Paste from Web Console)")
            quick_layout = QtWidgets.QVBoxLayout(quick_box)
            quick_layout.setSpacing(6)

            quick_desc = QtWidgets.QLabel("Copy the Client WebSocket URL from your TinyPOS web dashboard and paste it here:")
            quick_desc.setStyleSheet("color: #64748b; font-size: 11px;")
            quick_layout.addWidget(quick_desc)

            quick_input_row = QtWidgets.QHBoxLayout()
            self.input_quick = QtWidgets.QLineEdit()
            self.input_quick.setPlaceholderText("wss://pos.sayem.top/ws/client?api_key=...")
            btn_paste = QtWidgets.QPushButton("📋 Paste & Apply")
            btn_paste.setStyleSheet("background-color: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe;")
            btn_paste.clicked.connect(self._on_paste_quick)
            quick_input_row.addWidget(self.input_quick)
            quick_input_row.addWidget(btn_paste)
            quick_layout.addLayout(quick_input_row)
            main_layout.addWidget(quick_box)

            # 4. Connection Details
            details_box = QtWidgets.QGroupBox("Server & Terminal Configuration")
            details_layout = QtWidgets.QVBoxLayout(details_box)
            details_layout.setSpacing(6)

            details_layout.addWidget(QtWidgets.QLabel("Cloud Relay URL (e.g. wss://pos.sayem.top):"))
            self.input_server = QtWidgets.QLineEdit(config.server_url or "wss://pos.sayem.top")
            details_layout.addWidget(self.input_server)

            details_layout.addWidget(QtWidgets.QLabel("Client API Key (sk_client_...):"))
            key_row = QtWidgets.QHBoxLayout()
            self.input_key = QtWidgets.QLineEdit(config.client_api_key)
            self.input_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self.btn_toggle_key = QtWidgets.QPushButton("👁 Show")
            self.btn_toggle_key.setFixedWidth(75)
            self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
            key_row.addWidget(self.input_key)
            key_row.addWidget(self.btn_toggle_key)
            details_layout.addLayout(key_row)

            details_layout.addWidget(QtWidgets.QLabel("Terminal / Station Identifier:"))
            self.input_name = QtWidgets.QLineEdit(config.client_name or get_default_client_name())
            details_layout.addWidget(self.input_name)
            main_layout.addWidget(details_box)

            # 5. Live Test Status Label
            self.lbl_test_result = QtWidgets.QLabel("")
            self.lbl_test_result.setWordWrap(True)
            self.lbl_test_result.setStyleSheet("font-size: 12px; min-height: 18px;")
            main_layout.addWidget(self.lbl_test_result)

            # 6. Bottom Action Bar
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
            btn_close.clicked.connect(self.hide)
            btn_bar.addWidget(btn_close)

            btn_save = QtWidgets.QPushButton("💾 Save & Connect")
            btn_save.setObjectName("btnSave")
            btn_save.clicked.connect(self._on_save)
            btn_bar.addWidget(btn_save)

            main_layout.addLayout(btn_bar)

            # Initial status update
            self.update_status()

        def update_status(self, extra: Optional[Dict[str, Any]] = None):
            """Update live status display."""
            if not config.is_configured():
                self.lbl_relay_status.setText("Cloud Relay: ⚪ Not Configured")
                self.lbl_relay_status.setStyleSheet("color: #64748b; font-weight: bold;")
                self.lbl_group.setText("API Group: --")
                self.lbl_printer.setText("Printer: Configure server and key above")
                return

            if relay_worker.is_connected:
                group = relay_worker.current_group or "Pending..."
                self.lbl_relay_status.setText(f"Cloud Relay: 🟢 Connected ({config.server_url})")
                self.lbl_relay_status.setStyleSheet("color: #16a34a; font-weight: bold;")
                self.lbl_group.setText(f"API Group: {group}")

                if ble_driver.is_online:
                    rssi_str = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                    self.lbl_printer.setText(f"Printer: 🖨️ {ble_driver.device_name}{rssi_str} (Online)")
                    self.lbl_printer.setStyleSheet("color: #16a34a;")
                else:
                    self.lbl_printer.setText("Printer: 🟡 Scanning / Printer Offline")
                    self.lbl_printer.setStyleSheet("color: #d97706;")
            else:
                msg = relay_worker.last_status_message or "Connecting..."
                self.lbl_relay_status.setText(f"Cloud Relay: 🔴 {msg}")
                self.lbl_relay_status.setStyleSheet("color: #dc2626; font-weight: bold;")
                self.lbl_group.setText("API Group: --")
                if ble_driver.is_online:
                    self.lbl_printer.setText(f"Printer: 🖨️ {ble_driver.device_name} (Bluetooth Ready)")
                    self.lbl_printer.setStyleSheet("color: #16a34a;")
                else:
                    self.lbl_printer.setText("Printer: ⚪ Offline")
                    self.lbl_printer.setStyleSheet("color: #64748b;")

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

            if parsed and parsed.get("client_api_key"):
                if parsed.get("server_url"):
                    self.input_server.setText(parsed["server_url"])
                if parsed.get("client_api_key"):
                    self.input_key.setText(parsed["client_api_key"])
                if parsed.get("client_name"):
                    self.input_name.setText(parsed["client_name"])
                self.lbl_test_result.setStyleSheet("color: #16a34a; font-weight: bold;")
                self.lbl_test_result.setText("✅ Auto-filled credentials from WebSocket URL!")
            elif pasted.startswith("sk_client_"):
                self.input_key.setText(pasted)
                self.lbl_test_result.setStyleSheet("color: #16a34a; font-weight: bold;")
                self.lbl_test_result.setText("✅ Auto-filled Client API Key!")
            else:
                self.lbl_test_result.setStyleSheet("color: #d97706;")
                self.lbl_test_result.setText("⚠️ Could not extract credentials. Please fill manually.")

        def _on_feed_paper(self):
            relay_worker.feed_paper()

        def _on_reconnect_now(self):
            relay_worker.trigger_reconnect()

        def _on_test_connection(self):
            server_url = self.input_server.text().strip()
            api_key = self.input_key.text().strip()
            client_name = self.input_name.text().strip() or get_default_client_name()

            if not server_url or not api_key:
                self.lbl_test_result.setStyleSheet("color: #dc2626; font-weight: bold;")
                self.lbl_test_result.setText("❌ Please enter both Server URL and Client API Key.")
                return

            self.btn_test.setEnabled(False)
            self.lbl_test_result.setStyleSheet("color: #2563eb;")
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
                            group = data.get("group", "Unknown") if data.get("type") == "auth_success" else "Default"
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
                    col = "#16a34a" if success else "#dc2626"
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
                self.input_server.setText("")
                self.input_key.setText("")
                self.input_name.setText(config.client_name)
                self.input_quick.setText("")
                self.lbl_test_result.setStyleSheet("color: #d97706; font-weight: bold;")
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
            config.save()

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
            self.root.geometry("560x650")
            self.root.minsize(520, 580)
            self.root.configure(bg="#f8fafc")
            self.root.protocol("WM_DELETE_WINDOW", self.hide)

            container = tk.Frame(self.root, bg="#f8fafc", padx=24, pady=20)
            container.pack(fill="both", expand=True)

            # Header
            header_frame = tk.Frame(container, bg="#f8fafc")
            header_frame.pack(fill="x", pady=(0, 14))
            tk.Label(
                header_frame, text="TinyPOS Cloud Bridge",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 16, "bold"),
                bg="#f8fafc", fg="#0f172a"
            ).pack(anchor="w")
            tk.Label(
                header_frame, text="Connect your portable Bluetooth thermal printer to the TinyPOS Cloud.",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f8fafc", fg="#64748b"
            ).pack(anchor="w", pady=(2, 0))

            # Status Banner
            status_card = tk.LabelFrame(
                container, text=" Live Hardware & Cloud Status ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff", fg="#334155", padx=14, pady=10, relief="solid", bd=1
            )
            status_card.pack(fill="x", pady=(0, 14))

            self.lbl_relay_status = tk.Label(status_card, text="Cloud Relay: Connecting...", bg="#ffffff", fg="#334155")
            self.lbl_relay_status.pack(anchor="w", pady=1)
            self.lbl_group = tk.Label(status_card, text="API Group: --", bg="#ffffff", fg="#64748b")
            self.lbl_group.pack(anchor="w", pady=1)
            self.lbl_printer = tk.Label(status_card, text="Printer: Scanning Bluetooth...", bg="#ffffff", fg="#334155")
            self.lbl_printer.pack(anchor="w", pady=1)

            action_bar = tk.Frame(status_card, bg="#ffffff")
            action_bar.pack(anchor="w", pady=(6, 2))
            tk.Button(action_bar, text="📄 Feed Paper", command=self._on_feed_paper, padx=8, pady=2).pack(side="left", padx=(0, 8))
            tk.Button(action_bar, text="🔄 Reconnect Now", command=self._on_reconnect_now, padx=8, pady=2).pack(side="left")

            # Quick Connect
            quick_card = tk.LabelFrame(
                container, text=" Quick Connect (Paste from Web Console) ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff", fg="#334155", padx=14, pady=10, relief="solid", bd=1
            )
            quick_card.pack(fill="x", pady=(0, 14))
            tk.Label(quick_card, text="Paste the Client WebSocket URL from your web console:", bg="#ffffff", fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

            quick_row = tk.Frame(quick_card, bg="#ffffff")
            quick_row.pack(fill="x")
            self.ws_quick_var = tk.StringVar()
            tk.Entry(quick_row, textvariable=self.ws_quick_var).pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
            tk.Button(quick_row, text="📋 Paste & Apply", command=self._on_paste_quick, bg="#e0e7ff", fg="#3730a3").pack(side="right")

            # Details
            details_card = tk.LabelFrame(
                container, text=" Server & Terminal Configuration ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff", fg="#334155", padx=14, pady=10, relief="solid", bd=1
            )
            details_card.pack(fill="x", pady=(0, 14))

            tk.Label(details_card, text="Cloud Relay URL:", bg="#ffffff").pack(anchor="w")
            self.server_url_var = tk.StringVar(value=config.server_url or "wss://pos.sayem.top")
            tk.Entry(details_card, textvariable=self.server_url_var).pack(fill="x", ipady=3, pady=(2, 6))

            tk.Label(details_card, text="Client API Key:", bg="#ffffff").pack(anchor="w")
            key_row = tk.Frame(details_card, bg="#ffffff")
            key_row.pack(fill="x", pady=(2, 6))
            self.api_key_var = tk.StringVar(value=config.client_api_key)
            self.entry_api_key = tk.Entry(key_row, textvariable=self.api_key_var, show="*")
            self.entry_api_key.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
            self.btn_show_key = tk.Button(key_row, text="👁 Show", command=self._toggle_show_key, padx=6)
            self.btn_show_key.pack(side="right")

            tk.Label(details_card, text="Terminal Identifier:", bg="#ffffff").pack(anchor="w")
            self.client_name_var = tk.StringVar(value=config.client_name or get_default_client_name())
            tk.Entry(details_card, textvariable=self.client_name_var).pack(fill="x", ipady=3, pady=(2, 4))

            # Test Label
            self.lbl_test_result = tk.Label(container, text="", bg="#f8fafc", fg="#64748b", wraplength=480, justify="left")
            self.lbl_test_result.pack(anchor="w", pady=(0, 6))

            # Bottom Bar
            btn_bar = tk.Frame(container, bg="#f8fafc")
            btn_bar.pack(fill="x", pady=(4, 0))

            self.btn_test = tk.Button(btn_bar, text="🧪 Test Connection", command=self._on_test_connection, padx=8, pady=4)
            self.btn_test.pack(side="left")

            btn_remove = tk.Button(btn_bar, text="🗑️ Remove Config", command=self._on_remove_config, bg="#fee2e2", fg="#b91c1c", padx=8, pady=4)
            btn_remove.pack(side="left", padx=(8, 0))

            btn_save = tk.Button(btn_bar, text="💾 Save & Connect", command=self._on_save, bg="#10b981", fg="#ffffff", padx=14, pady=4)
            btn_save.pack(side="right", padx=(8, 0))

            btn_close = tk.Button(btn_bar, text="Close", command=self.hide, padx=10, pady=4)
            btn_close.pack(side="right")

            self.update_status()

        def show(self):
            if not self.root:
                return
            self._is_visible = True
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
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
                if not config.is_configured():
                    self.lbl_relay_status.config(text="Cloud Relay: ⚪ Not Configured", fg="#64748b")
                    self.lbl_group.config(text="API Group: --", fg="#64748b")
                    self.lbl_printer.config(text="Printer: Configure server and key above", fg="#64748b")
                    return
                if relay_worker.is_connected:
                    group = relay_worker.current_group or "Pending..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🟢 Connected ({config.server_url})", fg="#16a34a")
                    self.lbl_group.config(text=f"API Group: {group}", fg="#334155")
                    if ble_driver.is_online:
                        rssi = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                        self.lbl_printer.config(text=f"Printer: 🖨️ {ble_driver.device_name}{rssi} (Online)", fg="#16a34a")
                    else:
                        self.lbl_printer.config(text="Printer: 🟡 Scanning / Printer Offline", fg="#d97706")
                else:
                    msg = relay_worker.last_status_message or "Connecting..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🔴 {msg}", fg="#dc2626")
                    self.lbl_group.config(text="API Group: --", fg="#64748b")
                    self.lbl_printer.config(text=f"Printer: {'Online' if ble_driver.is_online else 'Offline'}", fg="#64748b")

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

        def _on_remove_config(self):
            if messagebox.askyesno("Remove Configuration", "Are you sure you want to delete your stored server credentials and disconnect?"):
                config.delete()
                self.server_url_var.set("")
                self.api_key_var.set("")
                self.client_name_var.set(config.client_name)
                self.ws_quick_var.set("")
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
                            group = data.get("group", "Unknown") if data.get("type") == "auth_success" else "Default"
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
            config.save()
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
