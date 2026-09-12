"""
PyQt6 Settings & Control Panel GUI for TinyPOS Client (Linux & Windows).
Modern, dark/light theme aware dialog with Bluetooth thermal printer selector and WebSocket testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.parse
from typing import Any, Callable, Dict, Optional

from core.config import config, get_default_client_name
from core.ble_driver import ble_driver
from core.relay_worker import relay_worker
from .theme import detect_system_dark_theme
from .styles import get_qt_dialog_stylesheet

logger = logging.getLogger("tinypos.ui.qt_settings")

PYQT_AVAILABLE = False
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    PYQT_AVAILABLE = True
except (ImportError, ModuleNotFoundError, Exception):
    PYQT_AVAILABLE = False


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
            self.input_quick.setPlaceholderText("wss://your-pos-server.com/ws/client?api_key=...")
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

            details_layout.addWidget(QtWidgets.QLabel("Cloud Relay URL (e.g. wss://your-pos-server.com):"))
            self.input_server = QtWidgets.QLineEdit(config.server_url or "wss://your-pos-server.com")
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

else:
    class QtSettingsDialog:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            logger.error("PyQt6 is not installed on this system.")
        def hide(self):
            pass
        def update_status(self, *args, **kwargs):
            pass
