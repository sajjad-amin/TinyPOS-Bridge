"""
Native macOS Cocoa Settings & Control Panel Dialog for TinyPOS Client.
Built with PyObjC / AppKit for 100% native macOS appearance, dark mode, and keyboard navigation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

import AppKit
import objc
import websockets

from core.config import config
from core.ble_driver import ble_driver
from core.relay_worker import relay_worker

logger = logging.getLogger("tinypos.ui.mac_settings")


class MacSettingsController(AppKit.NSObject):
    """Controller managing the native macOS Cocoa Settings window and its controls."""

    def init(self):
        self = objc.super(MacSettingsController, self).init()
        if self is None:
            return None

        self.settings_window: Optional[AppKit.NSWindow] = None
        self.status_callback: Optional[Callable[[Any], None]] = None

        # Settings UI controls
        self.ws_quick_input: Optional[AppKit.NSTextField] = None
        self.server_url_input: Optional[AppKit.NSTextField] = None
        self.api_key_input: Optional[AppKit.NSTextField] = None
        self.client_name_input: Optional[AppKit.NSTextField] = None
        self.printer_popup: Optional[AppKit.NSPopUpButton] = None
        self.printer_scan_btn: Optional[AppKit.NSButton] = None
        self.printer_hint: Optional[AppKit.NSTextField] = None
        self.test_status_label: Optional[AppKit.NSTextField] = None
        self.test_btn: Optional[AppKit.NSButton] = None
        self._popup_printer_items: List[Dict[str, str]] = []

        return self

    def show(self, status_callback: Optional[Callable[[Any], None]] = None):
        """Display the native Cocoa preferences/settings dialog."""
        if status_callback:
            self.status_callback = status_callback

        if self.settings_window:
            if self.server_url_input:
                self.server_url_input.setStringValue_(config.server_url or "")
            if self.api_key_input:
                self.api_key_input.setStringValue_(config.client_api_key or "")
            if self.client_name_input:
                self.client_name_input.setStringValue_(config.client_name or "")
            if self.ws_quick_input:
                self.ws_quick_input.setStringValue_("")
            if self.test_status_label:
                self.test_status_label.setStringValue_("")
            self._populatePrinterPopup()
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
        self.ws_quick_input.setPlaceholderString_("wss://your-pos-server.com/ws/client?api_key=sk_client_...")
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
        self.server_url_input.setPlaceholderString_("e.g. https://your-pos-server.com")
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
        self._popup_printer_items = []

        # Index 0: Automatic fallback to closest
        self.printer_popup.addItemWithTitle_("⚡ Auto: Closest (Strongest RSSI)")
        self._popup_printer_items.append({"name": "", "address": ""})

        seen = set()
        saved_addr = (config.printer_address or "").strip()
        if saved_addr:
            saved_name = (config.printer_name or "Saved Printer").strip()
            title = f"🖨️ {saved_name} ({saved_addr}) [Selected]"
            self.printer_popup.addItemWithTitle_(title)
            self._popup_printer_items.append({"name": saved_name, "address": saved_addr})
            seen.add(saved_addr.lower())

        items = printers if printers is not None else ble_driver.discovered_printers
        for p in items:
            addr = (p.get("address") or "").strip()
            if not addr or addr.lower() in seen:
                continue
            seen.add(addr.lower())
            p_name = (p.get("name") or "Thermal Printer").strip()
            rssi_str = f" [{p['rssi']} dBm]" if p.get("rssi") is not None else ""
            title = f"🖨️ {p_name} ({addr}){rssi_str}"
            self.printer_popup.addItemWithTitle_(title)
            self._popup_printer_items.append({"name": p_name, "address": addr})

        # Select saved item if configured, else default to index 0 (Auto)
        selected_idx = 0
        if saved_addr:
            for i, p_info in enumerate(self._popup_printer_items):
                if p_info["address"].lower() == saved_addr.lower():
                    selected_idx = i
                    break
        self.printer_popup.selectItemAtIndex_(selected_idx)

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
            if self.ws_quick_input:
                self.ws_quick_input.setStringValue_(clip_text.strip())
            self.parseWsUrlAction_(sender)
        else:
            if self.test_status_label:
                self.test_status_label.setTextColor_(AppKit.NSColor.systemRedColor())
                self.test_status_label.setStringValue_("⚠️ Clipboard is empty or contains no text.")

    def parseWsUrlAction_(self, sender):
        """Parse full WebSocket URL pasted into quick setup box."""
        if not self.ws_quick_input:
            return
        raw_val = self.ws_quick_input.stringValue().strip()
        if not raw_val:
            return

        parsed = config.parse_ws_url(raw_val)
        if parsed.get("server_url") and self.server_url_input:
            self.server_url_input.setStringValue_(parsed["server_url"])
        if parsed.get("client_api_key") and self.api_key_input:
            self.api_key_input.setStringValue_(parsed["client_api_key"])
        if parsed.get("client_name") and self.client_name_input:
            self.client_name_input.setStringValue_(parsed["client_name"])

        if self.test_status_label:
            self.test_status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
            self.test_status_label.setStringValue_("✅ Connection details auto-filled from URL!")

    def testConnectionAction_(self, sender):
        """Asynchronously tests WebSocket connection with currently entered fields."""
        if not self.server_url_input or not self.api_key_input or not self.client_name_input:
            return
        srv_url = self.server_url_input.stringValue().strip()
        api_key = self.api_key_input.stringValue().strip()
        client_name = self.client_name_input.stringValue().strip() or "Test Terminal"

        if not srv_url or not api_key:
            if self.test_status_label:
                self.test_status_label.setTextColor_(AppKit.NSColor.systemRedColor())
                self.test_status_label.setStringValue_("❌ Please enter both Server URL and Client API Key.")
            return

        if self.test_btn:
            self.test_btn.setEnabled_(False)
        if self.test_status_label:
            self.test_status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            self.test_status_label.setStringValue_("⏳ Testing connection to cloud relay...")

        def _test():
            parsed = urllib.parse.urlparse(srv_url)
            ws_scheme = "ws" if parsed.scheme in ("http", "ws") else "wss"
            netloc = parsed.netloc or parsed.path.split("/")[0]
            query = urllib.parse.urlencode({"api_key": api_key, "client_name": client_name})
            full_url = f"{ws_scheme}://{netloc}/ws/client?{query}"

            async def _connect():
                try:
                    async with websockets.connect(full_url, close_timeout=4.0) as ws:
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
                if self.test_btn:
                    self.test_btn.setEnabled_(True)
                if self.test_status_label:
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
            ble_driver.reset_cache()
            if self.server_url_input:
                self.server_url_input.setStringValue_("")
            if self.api_key_input:
                self.api_key_input.setStringValue_("")
            if self.client_name_input:
                self.client_name_input.setStringValue_(config.client_name)
            if self.ws_quick_input:
                self.ws_quick_input.setStringValue_("")
            if hasattr(self, "printer_popup") and self.printer_popup:
                self.printer_popup.selectItemAtIndex_(0)
            if self.test_status_label:
                self.test_status_label.setTextColor_(AppKit.NSColor.systemOrangeColor())
                self.test_status_label.setStringValue_("⚪ Configuration removed. Disconnected.")
            if self.status_callback:
                self.status_callback(None)
            relay_worker.trigger_reconnect()

    def cancelSettingsAction_(self, sender):
        """Close settings window without saving."""
        if self.settings_window:
            self.settings_window.close()

    def saveSettingsAction_(self, sender):
        """Save settings to disk and trigger immediate reconnect."""
        if self.server_url_input:
            config.server_url = self.server_url_input.stringValue().strip()
        if self.api_key_input:
            config.client_api_key = self.api_key_input.stringValue().strip()
        if self.client_name_input:
            config.client_name = self.client_name_input.stringValue().strip() or "Store Terminal"

        if hasattr(self, "printer_popup") and self.printer_popup:
            idx = self.printer_popup.indexOfSelectedItem()
            items = getattr(self, "_popup_printer_items", [])
            if 0 < idx < len(items):
                target = items[idx]
                config.printer_address = (target.get("address") or "").strip()
                config.printer_name = (target.get("name") or "").strip()
            else:
                config.printer_address = ""
                config.printer_name = ""

        config.save()
        ble_driver.reset_cache()
        logger.info(f"Saved configuration: server={config.server_url}, printer={config.printer_name} ({config.printer_address})")

        if self.settings_window:
            self.settings_window.close()

        if self.status_callback:
            self.status_callback(None)
        relay_worker.trigger_reconnect()
