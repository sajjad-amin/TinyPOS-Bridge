"""
Tkinter Fallback Settings & Control Panel GUI for TinyPOS Client.
Lightweight pure Python GUI used when PyQt6 is not installed on Linux or Windows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from typing import Any, Callable, Dict, Optional
import urllib.parse

from core.config import config, get_default_client_name
from core.ble_driver import ble_driver
from core.relay_worker import relay_worker
from .theme import detect_system_dark_theme

logger = logging.getLogger("tinypos.ui.tk_settings")

TK_AVAILABLE = False
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    TK_AVAILABLE = True
except (ImportError, ModuleNotFoundError, Exception):
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    TK_AVAILABLE = False


if TK_AVAILABLE:
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
            self.server_url_var = tk.StringVar(value=config.server_url or "wss://your-pos-server.com")
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
    class TkSettingsWindow:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            logger.error("Tkinter is not available on this system.")
        def hide(self):
            pass
        def update_status(self, *args, **kwargs):
            pass
