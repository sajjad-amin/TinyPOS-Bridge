"""
Native macOS Menu Bar Application for TinyPOS Client.
Built with PyObjC / Cocoa AppKit for 100% native macOS look, menu bar item, and dark mode.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import AppKit
import objc
from PyObjCTools import AppHelper

from core.config import config
from core.ble_driver import ble_driver
from core.relay_worker import relay_worker
from .mac_settings import MacSettingsController

logger = logging.getLogger("tinypos.ui.mac_tray")


def create_circle_icon(color_hex: str) -> AppKit.NSImage:
    """Render a crisp 18x18 macOS status bar icon with a colored circular badge."""
    size = AppKit.NSMakeSize(18, 18)
    image = AppKit.NSImage.alloc().initWithSize_(size)
    image.lockFocus()

    # Color definitions
    colors = {
        "green": AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.18, 0.80, 0.38, 1.0),
        "yellow": AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.96, 0.72, 0.15, 1.0),
        "red": AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.92, 0.26, 0.22, 1.0),
        "gray": AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.60, 0.60, 1.0),
    }
    col = colors.get(color_hex, colors["gray"])

    # Draw outer ring for crisp contrast in both light and dark mode
    stroke_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(AppKit.NSMakeRect(3.5, 3.5, 11, 11))
    AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.2, 0.35).set()
    stroke_path.stroke()

    # Fill center color
    col.set()
    oval_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(AppKit.NSMakeRect(4, 4, 10, 10))
    oval_path.fill()

    image.unlockFocus()
    return image


class MacTrayApp(AppKit.NSObject):
    """Mac Menu Bar / System Tray Application Controller."""

    def init(self):
        self = objc.super(MacTrayApp, self).init()
        if self is None:
            return None

        self.status_item: Optional[AppKit.NSStatusItem] = None
        self.menu: Optional[AppKit.NSMenu] = None
        self.header_item: Optional[AppKit.NSMenuItem] = None
        self.group_item: Optional[AppKit.NSMenuItem] = None
        self.printer_item: Optional[AppKit.NSMenuItem] = None

        # Settings Controller
        self.settings_controller = MacSettingsController.alloc().init()

        # Cached icon images
        self.icon_green = create_circle_icon("green")
        self.icon_yellow = create_circle_icon("yellow")
        self.icon_red = create_circle_icon("red")
        self.icon_gray = create_circle_icon("gray")

        return self

    def setupMenu(self):
        """Construct the macOS Menu Bar status item and its drop-down menu."""
        self.status_item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSSquareStatusItemLength)
        self.status_item.button().setImage_(self.icon_gray)
        self.status_item.button().setToolTip_("TinyPOS Cloud Bridge")

        self.menu = AppKit.NSMenu.alloc().init()

        # Status & Group Header
        self.header_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "TinyPOS Bridge: Initializing...", None, ""
        )
        self.header_item.setEnabled_(False)
        self.menu.addItem_(self.header_item)

        self.group_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "API Group: --", None, ""
        )
        self.group_item.setEnabled_(False)
        self.menu.addItem_(self.group_item)

        self.printer_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Printer: Scanning Bluetooth...", None, ""
        )
        self.printer_item.setEnabled_(False)
        self.menu.addItem_(self.printer_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Action: Feed Paper
        feed_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Feed Paper", "feedPaperAction:", ""
        )
        feed_item.setTarget_(self)
        self.menu.addItem_(feed_item)

        # Action: Reconnect
        reconnect_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reconnect Now", "reconnectAction:", "r"
        )
        reconnect_item.setTarget_(self)
        self.menu.addItem_(reconnect_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # Action: Preferences / Settings
        settings_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings...", "openSettingsAction:", ","
        )
        settings_item.setTarget_(self)
        self.menu.addItem_(settings_item)

        # Action: Quit
        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit TinyPOS Client", "quitAction:", "q"
        )
        quit_item.setTarget_(self)
        self.menu.addItem_(quit_item)

        self.status_item.setMenu_(self.menu)

        # Connect relay worker status callback
        relay_worker.set_status_callback(self.onStatusUpdate)

        # Update initial UI state
        self.updateStatusUI_(None)

        # If unconfigured on first start, open settings window immediately
        if not config.is_configured():
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, "openSettingsAction:", None, False
            )

    @objc.python_method
    def onStatusUpdate(self, state: str, info: Dict[str, Any]):
        """Thread-safe dispatch to update macOS menu bar from worker threads."""
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateStatusUI:", None, False
        )

    def updateStatusUI_(self, sender):
        """Update the menu items and icon on the main UI thread."""
        if not self.status_item:
            return

        if not config.is_configured():
            self.status_item.button().setImage_(self.icon_gray)
            self.header_item.setTitle_("TinyPOS Bridge: Not Configured")
            self.group_item.setTitle_("API Group: --")
            self.printer_item.setTitle_("Printer: Click Settings to configure")
            return

        if relay_worker.is_connected:
            group_name = relay_worker.current_group or "Pending..."
            self.group_item.setTitle_(f"API Group: {group_name}")

            if ble_driver.is_online:
                # 🟢 Connected to relay and printer ready
                self.status_item.button().setImage_(self.icon_green)
                rssi_str = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                printer_name = ble_driver.device_name or "X6 Thermal"
                self.header_item.setTitle_("TinyPOS Bridge: Active Target")
                self.printer_item.setTitle_(f"Printer: {printer_name}{rssi_str}")
            else:
                # 🟡 Connected to relay, but printer is offline
                self.status_item.button().setImage_(self.icon_yellow)
                self.header_item.setTitle_("TinyPOS Bridge: Standby (Printer Off)")
                self.printer_item.setTitle_("Printer: Out of Bluetooth range / Off")
        else:
            # 🔴 Disconnected from cloud relay
            self.status_item.button().setImage_(self.icon_red)
            msg = relay_worker.last_status_message or "Connecting..."
            self.header_item.setTitle_(f"TinyPOS Bridge: {msg}")
            self.group_item.setTitle_("API Group: --")
            if ble_driver.is_online:
                self.printer_item.setTitle_(f"Printer: {ble_driver.device_name} (Ready)")
            else:
                self.printer_item.setTitle_("Printer: Offline")

    def openSettingsAction_(self, sender):
        """Open the native Cocoa preferences/settings dialog."""
        if self.settings_controller:
            self.settings_controller.show(self.updateStatusUI_)

    def feedPaperAction_(self, sender):
        """Trigger paper feed safely via relay worker thread."""
        relay_worker.feed_paper()

    def reconnectAction_(self, sender):
        """Trigger immediate reconnect."""
        relay_worker.trigger_reconnect()

    def quitAction_(self, sender):
        """Terminate the application."""
        relay_worker.stop()
        AppKit.NSApplication.sharedApplication().terminate_(self)


def setup_main_menu(app: AppKit.NSApplication):
    """Install standard Edit menu into NSApp.mainMenu so Cmd+C/V/X/A/Z shortcuts work across all NSTextFields."""
    main_menu = AppKit.NSMenu.alloc().init()

    # 1. Application Menu
    app_menu_item = AppKit.NSMenuItem.alloc().init()
    app_menu = AppKit.NSMenu.alloc().initWithTitle_("TinyPOS")
    app_menu.addItemWithTitle_action_keyEquivalent_("Hide TinyPOS", "hide:", "h")
    app_menu.addItemWithTitle_action_keyEquivalent_("Hide Others", "hideOtherApplications:", "h")
    app_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    app_menu.addItemWithTitle_action_keyEquivalent_("Quit TinyPOS", "terminate:", "q")
    app_menu_item.setSubmenu_(app_menu)
    main_menu.addItem_(app_menu_item)

    # 2. Edit Menu (vital for standard macOS cut/copy/paste/select-all in Cocoa controls)
    edit_menu_item = AppKit.NSMenuItem.alloc().init()
    edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Undo", "undo:", "z")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
    edit_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
    edit_menu_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_menu_item)

    app.setMainMenu_(main_menu)


def run_mac_app():
    """Start the native Cocoa menu bar application on macOS."""
    logger.info("Starting native macOS menu bar application...")

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    setup_main_menu(app)

    delegate = MacTrayApp.alloc().init()
    app.setDelegate_(delegate)

    delegate.setupMenu()

    relay_worker.start()

    AppHelper.runEventLoop()
