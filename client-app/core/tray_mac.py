"""
Native macOS Menu Bar Application for TinyPOS Client
Built with PyObjC / Cocoa AppKit for 100% native macOS look and feel, dark mode, and zero external GUI dependencies.
"""

import asyncio
import json
import logging
import platform
import threading
from typing import Any, Dict, Optional
import urllib.parse

import AppKit
import objc
from PyObjCTools import AppHelper
import websockets

from .config import config
from .ble_driver import ble_driver
from .relay_worker import relay_worker

logger = logging.getLogger("tinypos.client.mac")


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
    def init(self):
        self = objc.super(MacTrayApp, self).init()
        if self is None:
            return None

        self.status_item = None
        self.menu = None
        self.header_item = None
        self.group_item = None
        self.printer_item = None
        self.settings_window = None

        # Settings UI controls
        self.ws_quick_input = None
        self.server_url_input = None
        self.api_key_input = None
        self.client_name_input = None
        self.test_status_label = None
        self.test_btn = None

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

    # --- Menu Actions ---

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

    def openSettingsAction_(self, sender):
        """Open the native Cocoa preferences/settings dialog."""
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.makeKeyAndOrderFront_(None)
            AppKit.NSApp.activateIgnoringOtherApps_(True)
            return

        # Create window
        rect = AppKit.NSMakeRect(0, 0, 520, 480)
        self.settings_window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.settings_window.setTitle_("TinyPOS Client Settings")
        self.settings_window.center()
        self.settings_window.setReleasedWhenClosed_(False)

        content = self.settings_window.contentView()

        # 1. Header Title & Description
        title_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 430, 470, 26))
        title_label.setStringValue_("TinyPOS Cloud Bridge Configuration")
        title_label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(16))
        title_label.setEditable_(False)
        title_label.setBezeled_(False)
        title_label.setDrawsBackground_(False)
        content.addSubview_(title_label)

        sub_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 410, 470, 18))
        sub_label.setStringValue_("Connect your local thermal printer to any TinyPOS cloud or local server.")
        sub_label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        sub_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        sub_label.setEditable_(False)
        sub_label.setBezeled_(False)
        sub_label.setDrawsBackground_(False)
        content.addSubview_(sub_label)

        # 2. Quick Setup Box (Paste WebSocket URL)
        box_rect = AppKit.NSMakeRect(20, 305, 480, 95)
        box = AppKit.NSBox.alloc().initWithFrame_(box_rect)
        box.setTitle_("Quick Setup (Paste WebSocket URL)")
        if box.titleCell():
            box.titleCell().setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
        box_view = box.contentView()

        ws_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(10, 45, 450, 16))
        ws_label.setStringValue_("Paste full connection URL copied from Settings page:")
        ws_label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        ws_label.setEditable_(False)
        ws_label.setBezeled_(False)
        ws_label.setDrawsBackground_(False)
        box_view.addSubview_(ws_label)

        self.ws_quick_input = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(10, 16, 260, 24))
        self.ws_quick_input.setPlaceholderString_("wss://pos.sayem.top/ws/client?api_key=sk_client_...")
        box_view.addSubview_(self.ws_quick_input)

        paste_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(275, 14, 95, 26))
        paste_btn.setTitle_("📋 Paste")
        paste_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        paste_btn.setTarget_(self)
        paste_btn.setAction_("pasteClipboardAction:")
        box_view.addSubview_(paste_btn)

        parse_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(375, 14, 90, 26))
        parse_btn.setTitle_("Auto-Fill")
        parse_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        parse_btn.setTarget_(self)
        parse_btn.setAction_("parseWsUrlAction:")
        box_view.addSubview_(parse_btn)

        content.addSubview_(box)

        # 3. Server URL Field
        srv_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 265, 150, 18))
        srv_label.setStringValue_("Cloud Server URL:")
        srv_label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        srv_label.setEditable_(False)
        srv_label.setBezeled_(False)
        srv_label.setDrawsBackground_(False)
        content.addSubview_(srv_label)

        self.server_url_input = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(180, 263, 315, 24))
        self.server_url_input.setPlaceholderString_("e.g. https://pos.sayem.top")
        self.server_url_input.setStringValue_(config.server_url or "")
        content.addSubview_(self.server_url_input)

        # 4. Client API Key Field
        key_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 225, 150, 18))
        key_label.setStringValue_("Client API Key:")
        key_label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        key_label.setEditable_(False)
        key_label.setBezeled_(False)
        key_label.setDrawsBackground_(False)
        content.addSubview_(key_label)

        self.api_key_input = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(180, 223, 315, 24))
        self.api_key_input.setPlaceholderString_("sk_client_...")
        self.api_key_input.setStringValue_(config.client_api_key or "")
        content.addSubview_(self.api_key_input)

        # 5. Terminal / Client Name Field
        name_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 185, 150, 18))
        name_label.setStringValue_("Terminal Name:")
        name_label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        name_label.setEditable_(False)
        name_label.setBezeled_(False)
        name_label.setDrawsBackground_(False)
        content.addSubview_(name_label)

        self.client_name_input = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(180, 183, 315, 24))
        self.client_name_input.setPlaceholderString_("e.g. Mac Mini, Office Counter")
        self.client_name_input.setStringValue_(config.client_name or "")
        content.addSubview_(self.client_name_input)

        # 6. Target Bluetooth Printer Field
        printer_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 142, 150, 18))
        printer_label.setStringValue_("Target Printer:")
        printer_label.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        printer_label.setEditable_(False)
        printer_label.setBezeled_(False)
        printer_label.setDrawsBackground_(False)
        content.addSubview_(printer_label)

        self.printer_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(AppKit.NSMakeRect(180, 138, 220, 26), False)
        self._populatePrinterPopup()
        content.addSubview_(self.printer_popup)

        self.printer_scan_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(405, 138, 90, 26))
        self.printer_scan_btn.setTitle_("🔍 Scan")
        self.printer_scan_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        self.printer_scan_btn.setTarget_(self)
        self.printer_scan_btn.setAction_("scanPrintersAction:")
        content.addSubview_(self.printer_scan_btn)

        self.printer_hint = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(180, 118, 315, 16))
        self.printer_hint.setStringValue_("💡 Falls back to closest printer if target offline")
        self.printer_hint.setFont_(AppKit.NSFont.systemFontOfSize_(10))
        self.printer_hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self.printer_hint.setEditable_(False)
        self.printer_hint.setBezeled_(False)
        self.printer_hint.setDrawsBackground_(False)
        content.addSubview_(self.printer_hint)

        # 7. Test Status Label
        self.test_status_label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(25, 80, 470, 22))
        self.test_status_label.setStringValue_("")
        self.test_status_label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        self.test_status_label.setEditable_(False)
        self.test_status_label.setBezeled_(False)
        self.test_status_label.setDrawsBackground_(False)
        content.addSubview_(self.test_status_label)

        # 8. Action Buttons (Bottom Bar)
        self.test_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(20, 25, 125, 32))
        self.test_btn.setTitle_("Test Connection")
        self.test_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        self.test_btn.setTarget_(self)
        self.test_btn.setAction_("testConnectionAction:")
        content.addSubview_(self.test_btn)

        remove_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(150, 25, 125, 32))
        remove_btn.setTitle_("Remove Config")
        remove_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        remove_btn.setTarget_(self)
        remove_btn.setAction_("removeConfigAction:")
        content.addSubview_(remove_btn)

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(285, 25, 95, 32))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelSettingsAction:")
        content.addSubview_(cancel_btn)

        save_btn = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(385, 25, 120, 32))
        save_btn.setTitle_("Save & Connect")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")  # Default enter key action
        save_btn.setTarget_(self)
        save_btn.setAction_("saveSettingsAction:")
        content.addSubview_(save_btn)

        self.settings_window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _populatePrinterPopup(self, printers=None):
        if not hasattr(self, "printer_popup") or not self.printer_popup:
            return
        self.printer_popup.removeAllItems()
        self.printer_popup.addItemWithTitle_("⚡ Auto: Closest (Strongest RSSI)")
        self.printer_popup.lastItem().setRepresentedObject_("")

        seen = set()
        saved_addr = (config.printer_address or "").strip()
        if saved_addr:
            title = f"🖨️ {config.printer_name or 'Saved Printer'} ({saved_addr})"
            self.printer_popup.addItemWithTitle_(title)
            self.printer_popup.lastItem().setRepresentedObject_(saved_addr)
            seen.add(saved_addr.lower())

        items = printers if printers is not None else ble_driver.discovered_printers
        for p in items:
            addr = (p.get("address") or "").strip()
            if not addr or addr.lower() in seen:
                continue
            seen.add(addr.lower())
            rssi_str = f" [{p['rssi']} dBm]" if p.get("rssi") is not None else ""
            title = f"🖨️ {p.get('name', 'Printer')} ({addr}){rssi_str}"
            self.printer_popup.addItemWithTitle_(title)
            self.printer_popup.lastItem().setRepresentedObject_(addr)

        # Select saved item if present
        if saved_addr:
            for i in range(self.printer_popup.numberOfItems()):
                item = self.printer_popup.itemAtIndex_(i)
                if item and str(item.representedObject() or "").lower() == saved_addr.lower():
                    self.printer_popup.selectItemAtIndex_(i)
                    break
        else:
            self.printer_popup.selectItemAtIndex_(0)

    def scanPrintersAction_(self, sender):
        """Asynchronously discover nearby printers and update popup button."""
        if hasattr(self, "printer_scan_btn") and self.printer_scan_btn:
            self.printer_scan_btn.setEnabled_(False)
            self.printer_scan_btn.setTitle_("Scanning...")

        def _scan():
            printers = asyncio.run(ble_driver.discover_printers(timeout=4.0))

            def _update():
                if hasattr(self, "printer_scan_btn") and self.printer_scan_btn:
                    self.printer_scan_btn.setEnabled_(True)
                    self.printer_scan_btn.setTitle_("🔍 Scan")
                self._populatePrinterPopup(printers)
                count = len(printers)
                msg = f"Found {count} printer{'s' if count != 1 else ''} nearby."
                if hasattr(self, "printer_hint") and self.printer_hint:
                    self.printer_hint.setStringValue_(f"✅ {msg} Fallback active.")

            self.performSelectorOnMainThread_withObject_waitUntilDone_("_execCallable:", _update, False)

        threading.Thread(target=_scan, daemon=True).start()

    def pasteClipboardAction_(self, sender):
        """Read system clipboard text directly and auto-fill connection parameters."""
        pb = AppKit.NSPasteboard.generalPasteboard()
        clip_text = pb.stringForType_(AppKit.NSPasteboardTypeString)
        if clip_text and clip_text.strip():
            self.ws_quick_input.setStringValue_(clip_text.strip())
            self.parseWsUrlAction_(sender)
        else:
            self.test_status_label.setTextColor_(AppKit.NSColor.systemRedColor())
            self.test_status_label.setStringValue_("⚠️ Clipboard is empty or contains no text.")

    def parseWsUrlAction_(self, sender):
        """Parse full WebSocket URL pasted into quick setup box."""
        raw_val = self.ws_quick_input.stringValue().strip()
        if not raw_val:
            return

        parsed = config.parse_ws_url(raw_val)
        if parsed.get("server_url"):
            self.server_url_input.setStringValue_(parsed["server_url"])
        if parsed.get("client_api_key"):
            self.api_key_input.setStringValue_(parsed["client_api_key"])
        if parsed.get("client_name"):
            self.client_name_input.setStringValue_(parsed["client_name"])

        self.test_status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
        self.test_status_label.setStringValue_("✅ Connection details auto-filled from URL!")

    def testConnectionAction_(self, sender):
        """Asynchronously tests WebSocket connection with currently entered fields."""
        srv_url = self.server_url_input.stringValue().strip()
        api_key = self.api_key_input.stringValue().strip()
        client_name = self.client_name_input.stringValue().strip() or "Test Terminal"

        if not srv_url or not api_key:
            self.test_status_label.setTextColor_(AppKit.NSColor.systemRedColor())
            self.test_status_label.setStringValue_("❌ Please enter both Server URL and Client API Key.")
            return

        self.test_btn.setEnabled_(False)
        self.test_status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self.test_status_label.setStringValue_("⏳ Testing connection to cloud relay...")

        def _test():
            # Build URL
            parsed = urllib.parse.urlparse(srv_url)
            ws_scheme = "ws" if parsed.scheme in ("http", "ws") else "wss"
            netloc = parsed.netloc or parsed.path.split("/")[0]
            query = urllib.parse.urlencode({"api_key": api_key, "client_name": client_name})
            full_url = f"{ws_scheme}://{netloc}/ws/client?{query}"

            async def _connect():
                try:
                    async with websockets.connect(full_url, close_timeout=4.0) as ws:
                        # Wait for welcome message
                        msg_str = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg_str)
                        group = data.get("group") or "Default"
                        return True, f"✅ Connected successfully! Assigned Group: '{group}'"
                except websockets.exceptions.InvalidStatusCode as e:
                    if e.status_code == 403:
                        return False, "❌ Server rejected connection: Invalid or unauthorized Client API Key (HTTP 403)."
                    return False, f"❌ Server returned HTTP error: {e.status_code}"
                except Exception as e:
                    return False, f"❌ Connection failed: {e}"

            success, message = asyncio.run(_connect())

            def _update():
                self.test_btn.setEnabled_(True)
                if success:
                    self.test_status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
                else:
                    self.test_status_label.setTextColor_(AppKit.NSColor.systemRedColor())
                self.test_status_label.setStringValue_(message)

            self.performSelectorOnMainThread_withObject_waitUntilDone_("_execCallable:", _update, False)

        threading.Thread(target=_test, daemon=True).start()

    def _execCallable_(self, func):
        func()

    def removeConfigAction_(self, sender):
        """Prompt confirmation and remove saved configuration from disk."""
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Remove Configuration?")
        alert.setInformativeText_("This will delete your saved Server URL and API Key from this Mac and disconnect from the cloud relay.")
        alert.addButtonWithTitle_("Remove Config")
        alert.addButtonWithTitle_("Cancel")
        alert.setAlertStyle_(AppKit.NSAlertStyleWarning)

        resp = alert.runModal()
        if resp == AppKit.NSAlertFirstButtonReturn:
            config.delete()
            self.server_url_input.setStringValue_("")
            self.api_key_input.setStringValue_("")
            self.client_name_input.setStringValue_(config.client_name)
            self.ws_quick_input.setStringValue_("")
            self.test_status_label.setTextColor_(AppKit.NSColor.systemOrangeColor())
            self.test_status_label.setStringValue_("⚪ Configuration removed. Disconnected.")
            self.updateStatusUI_(None)
            relay_worker.trigger_reconnect()

    def cancelSettingsAction_(self, sender):
        """Close settings window without saving."""
        if self.settings_window:
            self.settings_window.close()

    def saveSettingsAction_(self, sender):
        """Save settings to disk and trigger immediate reconnect."""
        config.server_url = self.server_url_input.stringValue().strip()
        config.client_api_key = self.api_key_input.stringValue().strip()
        config.client_name = self.client_name_input.stringValue().strip() or "Store Terminal"
        config.save()

        if self.settings_window:
            self.settings_window.close()

        self.updateStatusUI_(None)
        relay_worker.trigger_reconnect()


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

    # 2. Edit Menu (Enables standard Cmd+C, Cmd+V, Cmd+X, Cmd+A, Cmd+Z across Cocoa text fields)
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
    """Launch the native macOS Menu Bar application."""
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    setup_main_menu(app)

    delegate = MacTrayApp.alloc().init()
    app.setDelegate_(delegate)
    delegate.setupMenu()

    # Start the background relay worker
    relay_worker.start()

    logger.info("Starting TinyPOS macOS Menu Bar Application...")
    AppHelper.runEventLoop()
