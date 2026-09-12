"""
Cross-Platform System Tray & Control Application (Windows & Linux).
Uses native PyQt6 as the primary modern GUI and tray framework with zero external dependencies.
Falls back to Tkinter + Pystray if PyQt6 is not installed.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

from core.config import config
from core.ble_driver import ble_driver
from core.relay_worker import relay_worker
from .qt_settings import PYQT_AVAILABLE, QtSettingsDialog
from .tk_settings import TK_AVAILABLE, TkSettingsWindow

logger = logging.getLogger("tinypos.ui.crossplatform")


def run_pyqt_app():
    """Launch native PyQt6 application with System Tray and Control Panel dialog."""
    from PyQt6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. Custom status badge icons
    def create_tray_qicon(color_name: str = "gray") -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(64, 64)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        colors = {
            "green": QtGui.QColor(46, 204, 113),
            "yellow": QtGui.QColor(241, 196, 15),
            "red": QtGui.QColor(231, 76, 60),
            "gray": QtGui.QColor(149, 165, 166),
        }
        col = colors.get(color_name, colors["gray"])

        # Outer dark ring with white border
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 2))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(30, 30, 30, 220)))
        painter.drawEllipse(6, 6, 52, 52)

        # Inner colored circle
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(col))
        painter.drawEllipse(14, 14, 36, 36)
        painter.end()

        return QtGui.QIcon(pixmap)

    icon_green = create_tray_qicon("green")
    icon_yellow = create_tray_qicon("yellow")
    icon_red = create_tray_qicon("red")
    icon_gray = create_tray_qicon("gray")

    # 2. Thread-safe Signal Bridge for cross-thread relay updates
    class SignalBridge(QtCore.QObject):
        status_updated = QtCore.pyqtSignal(dict)

    bridge = SignalBridge()

    # 3. Native Settings Dialog
    dialog = QtSettingsDialog()

    # 4. System Tray Icon
    tray_icon = QtWidgets.QSystemTrayIcon()
    initial_icon = icon_gray if not config.is_configured() else icon_red
    tray_icon.setIcon(initial_icon)
    tray_icon.setToolTip("TinyPOS Cloud Bridge")

    # 5. Tray Menu
    menu = QtWidgets.QMenu()

    status_action = menu.addAction("TinyPOS: Connecting...")
    status_action.setEnabled(False)

    group_action = menu.addAction("API Group: --")
    group_action.setEnabled(False)

    printer_action = menu.addAction("Printer: Scanning Bluetooth...")
    printer_action.setEnabled(False)

    menu.addSeparator()

    def show_dialog():
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    settings_action = menu.addAction("⚙️ Settings & Control Panel...")
    settings_action.triggered.connect(show_dialog)

    feed_action = menu.addAction("📄 Feed Paper")
    feed_action.triggered.connect(relay_worker.feed_paper)

    reconnect_action = menu.addAction("🔄 Reconnect Now")
    reconnect_action.triggered.connect(relay_worker.trigger_reconnect)

    menu.addSeparator()

    def quit_app():
        logger.info("Terminating TinyPOS client...")
        relay_worker.stop()
        tray_icon.hide()
        app.quit()

    quit_action = menu.addAction("🚪 Quit TinyPOS Client")
    quit_action.triggered.connect(quit_app)

    tray_icon.setContextMenu(menu)

    # 6. Handle single/double click on tray icon
    def on_tray_activated(reason):
        if reason in (
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            show_dialog()

    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()

    # 7. Slot to update UI on main thread
    def handle_status_update(info: dict):
        if not config.is_configured():
            tray_icon.setIcon(icon_gray)
            status_action.setText("TinyPOS: ⚪ Not Configured")
            group_action.setText("API Group: --")
            printer_action.setText("Printer: Not Configured")
        elif relay_worker.is_connected:
            group_name = relay_worker.current_group or "Pending..."
            group_action.setText(f"API Group: {group_name}")
            if ble_driver.is_online:
                tray_icon.setIcon(icon_green)
                status_action.setText("TinyPOS: 🟢 Connected")
                rssi = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                printer_action.setText(f"Printer: 🖨️ {ble_driver.device_name}{rssi}")
            else:
                tray_icon.setIcon(icon_yellow)
                status_action.setText("TinyPOS: 🟡 Standby")
                printer_action.setText("Printer: ⚪ Offline / Scanning...")
        else:
            tray_icon.setIcon(icon_red)
            msg = relay_worker.last_status_message or "Connecting..."
            status_action.setText(f"TinyPOS: 🔴 {msg}")
            group_action.setText("API Group: --")
            printer_action.setText(f"Printer: {'Online' if ble_driver.is_online else 'Offline'}")

        dialog.update_status(info)

    bridge.status_updated.connect(handle_status_update)

    def on_worker_notify(state: str, info: dict):
        bridge.status_updated.emit(info)

    relay_worker.set_status_callback(on_worker_notify)
    relay_worker.start()

    # If unconfigured on start, open settings dialog automatically
    if not config.is_configured():
        show_dialog()

    logger.info("Starting TinyPOS PyQt6 application loop...")
    sys.exit(app.exec())


def run_tkinter_fallback_app():
    """Fallback using Tkinter + Pystray if PyQt6 is not installed."""
    import pystray
    from PIL import Image, ImageDraw
    import tkinter as tk

    def create_tray_icon_image(color_name: str = "gray") -> Image.Image:
        img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        colors = {
            "green": (46, 204, 113, 255),
            "yellow": (241, 196, 15, 255),
            "red": (231, 76, 60, 255),
            "gray": (149, 165, 166, 255),
        }
        fill_col = colors.get(color_name, colors["gray"])
        draw.ellipse((6, 6, 58, 58), fill=(30, 30, 30, 220), outline=(255, 255, 255, 180), width=2)
        draw.ellipse((14, 14, 50, 50), fill=fill_col)
        return img

    icon_green = create_tray_icon_image("green")
    icon_yellow = create_tray_icon_image("yellow")
    icon_red = create_tray_icon_image("red")
    icon_gray = create_tray_icon_image("gray")

    root = tk.Tk()
    settings_win = TkSettingsWindow()
    settings_win.init_ui(root)

    if config.is_configured():
        settings_win.hide()
    else:
        settings_win.show()

    def on_show_settings(item=None):
        root.after(0, settings_win.show)

    def on_quit(item=None):
        relay_worker.stop()
        icon.stop()
        root.after(0, root.destroy)

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"TinyPOS: {relay_worker.last_status_message}", None, enabled=False),
        pystray.MenuItem(lambda item: f"API Group: {relay_worker.current_group or '--'}", None, enabled=False),
        pystray.MenuItem(lambda item: f"Printer: {ble_driver.device_name or 'Offline'}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⚙️ Settings & Control Panel...", on_show_settings, default=True),
        pystray.MenuItem("📄 Feed Paper", lambda item: relay_worker.feed_paper()),
        pystray.MenuItem("🔄 Reconnect", lambda item: relay_worker.trigger_reconnect()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🚪 Quit TinyPOS Client", on_quit),
    )

    initial_icon = icon_gray if not config.is_configured() else icon_red
    icon = pystray.Icon("TinyPOS Client", icon=initial_icon, title="TinyPOS Cloud Bridge", menu=menu)

    def on_status_update(state: str, info: Dict[str, Any]):
        if not config.is_configured():
            icon.icon = icon_gray
        elif relay_worker.is_connected:
            icon.icon = icon_green if ble_driver.is_online else icon_yellow
        else:
            icon.icon = icon_red
        settings_win.update_status(info)

    relay_worker.set_status_callback(on_status_update)
    relay_worker.start()

    icon.run_detached()
    root.mainloop()


def run_crossplatform_app():
    """Select between PyQt6 and Tkinter backends."""
    if PYQT_AVAILABLE:
        logger.info("Launching with native PyQt6 GUI and System Tray.")
        run_pyqt_app()
    elif TK_AVAILABLE:
        logger.info("PyQt6 not detected. Falling back to Tkinter + Pystray.")
        run_tkinter_fallback_app()
    else:
        logger.critical("No desktop GUI toolkit available. Please install PyQt6: pip install PyQt6")
        sys.exit(1)
