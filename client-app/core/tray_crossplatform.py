"""
Cross-Platform System Tray & Control Application (Windows / Linux)
Combines pystray for taskbar/tray integration with Tkinter Control Panel & Settings dialog,
with dynamic status tooltips, zero-latency activation, and browser fallback.
"""

import logging
import sys
import threading
from typing import Any, Dict, Optional
from PIL import Image, ImageDraw

from .config import config
from .ble_driver import ble_driver
from .relay_worker import relay_worker
from .settings_window import TK_AVAILABLE, TkSettingsWindow, open_browser_settings

logger = logging.getLogger("tinypos.client.crossplatform")


def create_tray_icon_image(color_name: str = "gray") -> Image.Image:
    """Generate a clean 64x64 PIL icon with a circular color badge."""
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colors = {
        "green": (46, 204, 113, 255),
        "yellow": (241, 196, 15, 255),
        "red": (231, 76, 60, 255),
        "gray": (149, 165, 166, 255),
    }
    fill_col = colors.get(color_name, colors["gray"])

    # Outer dark border
    draw.ellipse((6, 6, 58, 58), fill=(30, 30, 30, 220), outline=(255, 255, 255, 180), width=2)
    # Inner colored status circle
    draw.ellipse((14, 14, 50, 50), fill=fill_col)

    return img


def run_crossplatform_app():
    """Launch system tray app with Tkinter Settings GUI on Windows / Linux."""
    logger.info(f"Initializing TinyPOS cross-platform client on {sys.platform} (Tkinter={TK_AVAILABLE})...")

    # Cached state icon images
    icon_green = create_tray_icon_image("green")
    icon_yellow = create_tray_icon_image("yellow")
    icon_red = create_tray_icon_image("red")
    icon_gray = create_tray_icon_image("gray")

    settings_win: Optional[TkSettingsWindow] = None
    root = None
    icon = None
    is_quitting = False

    # Setup Tkinter Root if available
    if TK_AVAILABLE:
        try:
            import tkinter as tk
            root = tk.Tk()
            settings_win = TkSettingsWindow()
            settings_win.init_ui(root)

            # Initially show or hide depending on whether configured
            if config.is_configured():
                settings_win.hide()
            else:
                logger.info("Client is not configured. Displaying Settings dialog on startup.")
                settings_win.show()
        except Exception as e:
            logger.warning(f"Failed to initialize Tkinter desktop window: {e}. Falling back to tray-only mode.")
            root = None
            settings_win = None

    def on_show_settings(item=None):
        """Open or focus the Settings & Control Panel window."""
        if settings_win and root:
            root.after(0, settings_win.show)
        else:
            open_browser_settings()

    def on_feed(item=None):
        relay_worker.feed_paper()

    def on_reconnect(item=None):
        relay_worker.trigger_reconnect()

    def on_quit(item=None):
        nonlocal is_quitting
        if is_quitting:
            return
        is_quitting = True
        logger.info("Stopping TinyPOS Client...")
        relay_worker.stop()
        if icon:
            try:
                icon.stop()
            except Exception:
                pass
        if root:
            try:
                root.after(0, root.destroy)
            except Exception:
                pass

    # Build Pystray System Tray Icon
    try:
        import pystray

        # Dynamic menu item text getters
        def get_status_text(item):
            if not config.is_configured():
                return "TinyPOS: Not Configured"
            if relay_worker.is_connected:
                return "TinyPOS: 🟢 Connected"
            return f"TinyPOS: 🔴 {relay_worker.last_status_message}"

        def get_group_text(item):
            return f"API Group: {relay_worker.current_group or '--'}"

        def get_printer_text(item):
            if ble_driver.is_online:
                rssi = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                return f"Printer: 🖨️ {ble_driver.device_name}{rssi}"
            return "Printer: ⚪ Offline"

        menu = pystray.Menu(
            pystray.MenuItem(get_status_text, None, enabled=False),
            pystray.MenuItem(get_group_text, None, enabled=False),
            pystray.MenuItem(get_printer_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            # default=True ensures single/double click on icon opens settings on Xorg & Windows!
            pystray.MenuItem("⚙️ Settings & Control Panel...", on_show_settings, default=True),
            pystray.MenuItem("📄 Feed Paper", on_feed),
            pystray.MenuItem("🔄 Reconnect", on_reconnect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🚪 Quit TinyPOS Client", on_quit),
        )

        initial_icon = icon_gray if not config.is_configured() else icon_red
        icon = pystray.Icon("TinyPOS Client", icon=initial_icon, title="TinyPOS Cloud Bridge", menu=menu)

    except Exception as e:
        logger.warning(f"Could not initialize system tray with pystray: {e}")
        icon = None

    # Status update callback from relay worker
    def on_status_update(state: str, info: Dict[str, Any]):
        if icon:
            try:
                if not config.is_configured():
                    icon.icon = icon_gray
                elif relay_worker.is_connected:
                    if ble_driver.is_online:
                        icon.icon = icon_green
                    else:
                        icon.icon = icon_yellow
                else:
                    icon.icon = icon_red
            except Exception:
                pass

        if settings_win:
            settings_win.update_status(info)

    relay_worker.set_status_callback(on_status_update)
    relay_worker.start()

    # Launch Application Loops
    if icon and root:
        # Both Tray and Tkinter GUI available
        try:
            icon.run_detached()
            logger.info("Pystray system tray loop detached; running Tkinter mainloop.")
            root.mainloop()
        except Exception as e:
            logger.error(f"Error in application loop: {e}")
            on_quit()
    elif icon:
        # Tray only (headless or no Tkinter)
        logger.info("Running in system tray only mode.")
        if not config.is_configured():
            open_browser_settings()
        icon.run()
    elif root:
        # Desktop Window only (no system tray support)
        logger.info("Running in desktop window only mode.")
        settings_win.show()
        root.mainloop()
    else:
        # Headless with web fallback
        logger.info("Running in headless console mode with web settings server.")
        if not config.is_configured():
            open_browser_settings()
        try:
            while not is_quitting:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            on_quit()
