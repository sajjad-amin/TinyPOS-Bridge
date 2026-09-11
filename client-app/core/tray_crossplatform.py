"""
Cross-Platform System Tray Application (Windows / Linux)
Uses pystray and Pillow for tray icon and system tray menu.
"""

import asyncio
import json
import logging
import sys
import threading
import time
from typing import Any, Dict
from PIL import Image, ImageDraw

from .config import config
from .ble_driver import ble_driver
from .relay_worker import relay_worker

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

    # Outer border
    draw.ellipse((8, 8, 56, 56), fill=(30, 30, 30, 200), outline=(255, 255, 255, 180), width=2)
    # Inner colored circle
    draw.ellipse((14, 14, 50, 50), fill=fill_col)

    return img


def run_crossplatform_app():
    """Launch system tray app using pystray on Windows / Linux."""
    try:
        import pystray
    except ImportError:
        print("[Error] pystray is required on Windows/Linux: pip install pystray")
        sys.exit(1)

    icon_green = create_tray_icon_image("green")
    icon_yellow = create_tray_icon_image("yellow")
    icon_red = create_tray_icon_image("red")
    icon_gray = create_tray_icon_image("gray")

    icon = pystray.Icon("TinyPOS Client", icon=icon_gray, title="TinyPOS Cloud Bridge")

    def on_feed(item):
        threading.Thread(target=lambda: asyncio.run(ble_driver.feed_paper()), daemon=True).start()

    def on_reconnect(item):
        relay_worker.trigger_reconnect()

    def on_quit(item):
        relay_worker.stop()
        icon.stop()

    def get_menu():
        status_text = f"Status: {relay_worker.last_status_message}"
        group_text = f"Group: {relay_worker.current_group or '--'}"
        printer_text = f"Printer: {ble_driver.device_name or 'Offline'}"
        if ble_driver.rssi:
            printer_text += f" ({ble_driver.rssi} dBm)"

        return pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem(group_text, None, enabled=False),
            pystray.MenuItem(printer_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Feed Paper", on_feed),
            pystray.MenuItem("Reconnect", on_reconnect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit TinyPOS Client", on_quit),
        )

    def on_status_update(state: str, info: Dict[str, Any]):
        if not config.is_configured():
            icon.icon = icon_gray
        elif relay_worker.is_connected:
            if ble_driver.is_online:
                icon.icon = icon_green
            else:
                icon.icon = icon_yellow
        else:
            icon.icon = icon_red
        icon.menu = get_menu()

    relay_worker.set_status_callback(on_status_update)
    relay_worker.start()

    icon.menu = get_menu()
    icon.run()
