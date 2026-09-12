from __future__ import annotations
"""
Cross-Platform Settings & Control Panel GUI for TinyPOS Client
Provides a native Tkinter preferences dialog on Windows and Linux,
with an automatic browser-based fallback if Tkinter is not installed.
"""

import asyncio
import http.server
import json
import logging
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from typing import Any, Callable, Dict, Optional

from .config import config, get_default_client_name
from .ble_driver import ble_driver
from .relay_worker import relay_worker

logger = logging.getLogger("tinypos.client.settings")

# Check if Tkinter is available
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


if TK_AVAILABLE:
    class TkSettingsWindow:
        """Tkinter-based Settings and Control Panel Dialog for Windows and Linux."""

        def __init__(self, on_save_callback: Optional[Callable[[], None]] = None):
            self.on_save_callback = on_save_callback
            self.root: Optional[Any] = None
            self._is_visible: bool = False
            self._show_key: bool = False

            # Form variables
            self.ws_quick_var: Optional[Any] = None
            self.server_url_var: Optional[Any] = None
            self.api_key_var: Optional[Any] = None
            self.client_name_var: Optional[Any] = None

            # Live status labels
            self.lbl_relay_status: Optional[Any] = None
            self.lbl_group: Optional[Any] = None
            self.lbl_printer: Optional[Any] = None
            self.lbl_test_result: Optional[Any] = None
            self.btn_test: Optional[Any] = None
            self.btn_show_key: Optional[Any] = None
            self.entry_api_key: Optional[Any] = None

        def init_ui(self, root: Any):
            """Build the Tkinter GUI layout."""
            self.root = root
            self.root.title("TinyPOS - Control Panel & Settings")
            self.root.geometry("560x640")
            self.root.minsize(520, 580)
            self.root.configure(bg="#f8fafc")

            # Intercept window close (hide rather than destroy)
            self.root.protocol("WM_DELETE_WINDOW", self.hide)

            # Style configuration
            style = ttk.Style()
            try:
                style.theme_use("clam")
            except Exception:
                pass

            # Container with padding
            container = tk.Frame(self.root, bg="#f8fafc", padx=24, pady=20)
            container.pack(fill="both", expand=True)

            # 1. Header
            header_frame = tk.Frame(container, bg="#f8fafc")
            header_frame.pack(fill="x", pady=(0, 14))

            title_lbl = tk.Label(
                header_frame,
                text="TinyPOS Cloud Bridge",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 16, "bold"),
                bg="#f8fafc",
                fg="#0f172a",
            )
            title_lbl.pack(anchor="w")

            sub_lbl = tk.Label(
                header_frame,
                text="Connect your portable Bluetooth thermal printer to the TinyPOS Cloud.",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f8fafc",
                fg="#64748b",
            )
            sub_lbl.pack(anchor="w", pady=(2, 0))

            # 2. Live Status & Control Banner
            status_card = tk.LabelFrame(
                container,
                text=" Live Hardware & Cloud Status ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff",
                fg="#334155",
                padx=14,
                pady=10,
                relief="solid",
                bd=1,
            )
            status_card.pack(fill="x", pady=(0, 14))

            self.lbl_relay_status = tk.Label(
                status_card, text="Cloud Relay: Connecting...", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff", fg="#334155"
            )
            self.lbl_relay_status.pack(anchor="w", pady=1)

            self.lbl_group = tk.Label(
                status_card, text="API Group: --", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff", fg="#64748b"
            )
            self.lbl_group.pack(anchor="w", pady=1)

            self.lbl_printer = tk.Label(
                status_card, text="Printer: Scanning Bluetooth...", font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff", fg="#334155"
            )
            self.lbl_printer.pack(anchor="w", pady=1)

            # Quick action buttons inside status banner
            action_bar = tk.Frame(status_card, bg="#ffffff")
            action_bar.pack(anchor="w", pady=(6, 2))

            btn_feed = tk.Button(
                action_bar,
                text="📄 Feed Paper",
                command=self._on_feed_paper,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f1f5f9",
                fg="#1e293b",
                relief="groove",
                cursor="hand2",
                padx=8,
                pady=2,
            )
            btn_feed.pack(side="left", padx=(0, 8))

            btn_reconnect = tk.Button(
                action_bar,
                text="🔄 Reconnect Now",
                command=self._on_reconnect_now,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f1f5f9",
                fg="#1e293b",
                relief="groove",
                cursor="hand2",
                padx=8,
                pady=2,
            )
            btn_reconnect.pack(side="left")

            # 3. Quick Connect (Copy-Paste)
            quick_card = tk.LabelFrame(
                container,
                text=" Quick Connect (Paste from Web Console) ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff",
                fg="#334155",
                padx=14,
                pady=10,
                relief="solid",
                bd=1,
            )
            quick_card.pack(fill="x", pady=(0, 14))

            quick_desc = tk.Label(
                quick_card,
                text="Copy the Client WebSocket URL from your TinyPOS web dashboard and paste it here:",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 8),
                bg="#ffffff",
                fg="#64748b",
                justify="left",
                wraplength=480,
            )
            quick_desc.pack(anchor="w", pady=(0, 6))

            quick_input_frame = tk.Frame(quick_card, bg="#ffffff")
            quick_input_frame.pack(fill="x")

            self.ws_quick_var = tk.StringVar()
            entry_quick = tk.Entry(
                quick_input_frame,
                textvariable=self.ws_quick_var,
                font=("Consolas" if sys.platform == "win32" else "Monospace", 9),
                bg="#f8fafc",
                fg="#0f172a",
                relief="solid",
                bd=1,
            )
            entry_quick.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

            btn_paste = tk.Button(
                quick_input_frame,
                text="📋 Paste & Apply",
                command=self._on_paste_quick,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#e0e7ff",
                fg="#3730a3",
                relief="groove",
                cursor="hand2",
                padx=10,
                pady=2,
            )
            btn_paste.pack(side="right")

            # 4. Connection Details
            details_card = tk.LabelFrame(
                container,
                text=" Server & Terminal Configuration ",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#ffffff",
                fg="#334155",
                padx=14,
                pady=10,
                relief="solid",
                bd=1,
            )
            details_card.pack(fill="x", pady=(0, 14))

            # Server URL
            tk.Label(
                details_card,
                text="Cloud Relay URL (e.g. wss://pos.sayem.top):",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff",
                fg="#1e293b",
            ).pack(anchor="w")

            self.server_url_var = tk.StringVar(value=config.server_url or "wss://pos.sayem.top")
            entry_server = tk.Entry(
                details_card,
                textvariable=self.server_url_var,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f8fafc",
                fg="#0f172a",
                relief="solid",
                bd=1,
            )
            entry_server.pack(fill="x", ipady=3, pady=(2, 8))

            # Client API Key
            tk.Label(
                details_card,
                text="Client API Key (sk_client_...):",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff",
                fg="#1e293b",
            ).pack(anchor="w")

            key_frame = tk.Frame(details_card, bg="#ffffff")
            key_frame.pack(fill="x", pady=(2, 8))

            self.api_key_var = tk.StringVar(value=config.client_api_key)
            self.entry_api_key = tk.Entry(
                key_frame,
                textvariable=self.api_key_var,
                show="*",
                font=("Consolas" if sys.platform == "win32" else "Monospace", 9),
                bg="#f8fafc",
                fg="#0f172a",
                relief="solid",
                bd=1,
            )
            self.entry_api_key.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))

            self.btn_show_key = tk.Button(
                key_frame,
                text="👁 Show",
                command=self._toggle_show_key,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 8),
                bg="#f1f5f9",
                fg="#334155",
                relief="groove",
                cursor="hand2",
                padx=6,
            )
            self.btn_show_key.pack(side="right")

            # Terminal Name
            tk.Label(
                details_card,
                text="Terminal / Station Identifier:",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#ffffff",
                fg="#1e293b",
            ).pack(anchor="w")

            self.client_name_var = tk.StringVar(value=config.client_name or get_default_client_name())
            entry_name = tk.Entry(
                details_card,
                textvariable=self.client_name_var,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9),
                bg="#f8fafc",
                fg="#0f172a",
                relief="solid",
                bd=1,
            )
            entry_name.pack(fill="x", ipady=3, pady=(2, 4))

            # 5. Test Connection & Bottom Buttons
            test_frame = tk.Frame(container, bg="#f8fafc")
            test_frame.pack(fill="x", pady=(0, 10))

            self.btn_test = tk.Button(
                test_frame,
                text="🧪 Test Connection",
                command=self._on_test_connection,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 9, "bold"),
                bg="#f1f5f9",
                fg="#0f172a",
                relief="groove",
                cursor="hand2",
                padx=10,
                pady=3,
            )
            self.btn_test.pack(side="left")

            self.lbl_test_result = tk.Label(
                test_frame,
                text="",
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 8),
                bg="#f8fafc",
                fg="#64748b",
                wraplength=350,
                justify="left",
            )
            self.lbl_test_result.pack(side="left", padx=(10, 0))

            # Bottom Bar (Save & Close)
            btn_bar = tk.Frame(container, bg="#f8fafc")
            btn_bar.pack(fill="x", pady=(6, 0))

            btn_save = tk.Button(
                btn_bar,
                text="💾 Save & Connect",
                command=self._on_save,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10, "bold"),
                bg="#10b981",
                fg="#ffffff",
                activebackground="#059669",
                activeforeground="#ffffff",
                relief="flat",
                cursor="hand2",
                padx=16,
                pady=6,
            )
            btn_save.pack(side="right", padx=(8, 0))

            btn_close = tk.Button(
                btn_bar,
                text="Close",
                command=self.hide,
                font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 10),
                bg="#e2e8f0",
                fg="#334155",
                relief="flat",
                cursor="hand2",
                padx=14,
                pady=6,
            )
            btn_close.pack(side="right")

            # Update initial status
            self.update_status()

        def show(self):
            """Make the Settings window visible and bring to front."""
            if not self.root:
                return
            self._is_visible = True
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.update_status()

        def hide(self):
            """Hide the Settings window (keeps app running in tray)."""
            if not self.root:
                return
            self._is_visible = False
            self.root.withdraw()

        def toggle(self):
            if self._is_visible:
                self.hide()
            else:
                self.show()

        def update_status(self, extra: Optional[Dict[str, Any]] = None):
            """Update live status labels in thread-safe manner."""
            if not self.root or not self.lbl_relay_status:
                return

            def _do():
                if not config.is_configured():
                    self.lbl_relay_status.config(text="Cloud Relay: ⚪ Not Configured", fg="#64748b")
                    self.lbl_group.config(text="API Group: --", fg="#64748b")
                    self.lbl_printer.config(text="Printer: Configure server and key above", fg="#64748b")
                    return

                if relay_worker.is_connected:
                    group_name = relay_worker.current_group or "Pending..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🟢 Connected ({config.server_url})", fg="#16a34a")
                    self.lbl_group.config(text=f"API Group: {group_name}", fg="#334155")

                    if ble_driver.is_online:
                        rssi_str = f" ({ble_driver.rssi} dBm)" if ble_driver.rssi else ""
                        self.lbl_printer.config(text=f"Printer: 🖨️ {ble_driver.device_name}{rssi_str} (Ready)", fg="#16a34a")
                    else:
                        self.lbl_printer.config(text="Printer: 🟡 Scanning / Printer Offline", fg="#d97706")
                else:
                    msg = relay_worker.last_status_message or "Connecting..."
                    self.lbl_relay_status.config(text=f"Cloud Relay: 🔴 {msg}", fg="#dc2626")
                    self.lbl_group.config(text="API Group: --", fg="#64748b")
                    if ble_driver.is_online:
                        self.lbl_printer.config(text=f"Printer: 🖨️ {ble_driver.device_name} (Bluetooth Ready)", fg="#16a34a")
                    else:
                        self.lbl_printer.config(text="Printer: ⚪ Offline", fg="#64748b")

            try:
                self.root.after(0, _do)
            except Exception:
                pass

        def _toggle_show_key(self):
            """Toggle password masking for API key entry."""
            self._show_key = not self._show_key
            if self._show_key:
                self.entry_api_key.config(show="")
                self.btn_show_key.config(text="🙈 Hide")
            else:
                self.entry_api_key.config(show="*")
                self.btn_show_key.config(text="👁 Show")

        def _on_paste_quick(self):
            """Read clipboard and parse WebSocket URL automatically."""
            try:
                pasted = self.root.clipboard_get().strip()
            except Exception:
                pasted = (self.ws_quick_var.get() if self.ws_quick_var else "").strip()

            if not pasted:
                pasted = (self.ws_quick_var.get() if self.ws_quick_var else "").strip()

            if not pasted:
                messagebox.showinfo("Clipboard Empty", "Please copy your WebSocket connection URL from the web console first.")
                return

            self.ws_quick_var.set(pasted)
            parsed = config.parse_ws_url(pasted)

            if parsed and parsed.get("client_api_key"):
                if parsed.get("server_url"):
                    self.server_url_var.set(parsed["server_url"])
                if parsed.get("client_api_key"):
                    self.api_key_var.set(parsed["client_api_key"])
                if parsed.get("client_name"):
                    self.client_name_var.set(parsed["client_name"])
                self.lbl_test_result.config(text="✅ Auto-filled credentials from WebSocket URL!", fg="#16a34a")
            elif pasted.startswith("sk_client_"):
                self.api_key_var.set(pasted)
                self.lbl_test_result.config(text="✅ Auto-filled API Key!", fg="#16a34a")
            else:
                self.lbl_test_result.config(text="⚠ Could not parse URL query parameters. Please enter manually.", fg="#d97706")

        def _on_feed_paper(self):
            relay_worker.feed_paper()

        def _on_reconnect_now(self):
            relay_worker.trigger_reconnect()

        def _on_test_connection(self):
            """Test the connection against the entered URL and API Key in a background thread."""
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
                    clean_url = server_url
                    parsed = urllib.parse.urlparse(clean_url)
                    scheme = "wss" if parsed.scheme.lower() in ("https", "wss") else "ws"
                    netloc = parsed.netloc or parsed.path.split("/")[0]
                    query = urllib.parse.urlencode({
                        "api_key": api_key,
                        "client_name": client_name,
                    })
                    ws_url = f"{scheme}://{netloc}/ws/client?{query}"

                    try:
                        async with websockets.connect(ws_url, open_timeout=6.0, close_timeout=2.0) as ws:
                            raw = await asyncio.wait_for(ws.recv(), timeout=4.0)
                            data = json.loads(raw)
                            if data.get("type") == "auth_success":
                                group = data.get("group", "Unknown")
                                return True, f"✅ Connected successfully! Group: '{group}'"
                            return True, "✅ Connected to Cloud Relay!"
                    except asyncio.TimeoutError:
                        return False, "❌ Connection timed out after 6 seconds."
                    except websockets.InvalidStatusCode as e:
                        if e.status_code == 403:
                            return False, "❌ Unauthorized: Invalid or inactive Client API Key (HTTP 403)."
                        return False, f"❌ Server returned HTTP {e.status_code}."
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
            """Save settings to disk and trigger immediate reconnect."""
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
    # Safe Fallback when Tkinter is not installed
    class TkSettingsWindow:
        def __init__(self, on_save_callback: Optional[Callable[[], None]] = None):
            self.root = None
            self.on_save_callback = on_save_callback

        def init_ui(self, root: Any):
            pass

        def show(self):
            open_browser_settings()

        def hide(self):
            pass

        def toggle(self):
            open_browser_settings()

        def update_status(self, extra: Optional[Dict[str, Any]] = None):
            pass


# Web fallback server for headless / minimal Linux environments
class WebConfigHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        status_text = "Connected" if relay_worker.is_connected else relay_worker.last_status_message
        printer_text = f"{ble_driver.device_name} (Online)" if ble_driver.is_online else "Offline"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>TinyPOS Client Settings</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 20px; display: flex; justify-content: center; }}
        .card {{ background: white; border-radius: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); width: 100%; max-width: 520px; padding: 24px; }}
        h2 {{ margin: 0 0 4px; color: #0f172a; font-size: 20px; }}
        p.sub {{ margin: 0 0 20px; color: #64748b; font-size: 13px; }}
        .status-box {{ background: #f1f5f9; border-radius: 6px; padding: 12px; margin-bottom: 20px; font-size: 13px; line-height: 1.6; color: #334155; }}
        label {{ display: block; font-weight: 600; font-size: 13px; margin: 12px 0 4px; color: #1e293b; }}
        input[type="text"], input[type="password"] {{ width: 100%; box-sizing: border-box; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; }}
        .btn-row {{ margin-top: 24px; display: flex; gap: 10px; justify-content: flex-end; }}
        button {{ padding: 10px 18px; border-radius: 6px; border: none; font-weight: 600; cursor: pointer; }}
        .btn-primary {{ background: #10b981; color: white; }}
        .btn-sec {{ background: #e2e8f0; color: #334155; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>TinyPOS Cloud Bridge</h2>
        <p class="sub">Configure printer bridge for this terminal.</p>
        <div class="status-box">
            <div><strong>Relay Status:</strong> {status_text}</div>
            <div><strong>API Group:</strong> {relay_worker.current_group or '--'}</div>
            <div><strong>Printer:</strong> {printer_text}</div>
        </div>
        <form method="POST" action="/save">
            <label>Server Relay URL</label>
            <input type="text" name="server_url" value="{config.server_url or 'wss://pos.sayem.top'}" required>
            <label>Client API Key</label>
            <input type="text" name="client_api_key" value="{config.client_api_key}" required>
            <label>Terminal / Station Name</label>
            <input type="text" name="client_name" value="{config.client_name or get_default_client_name()}">
            <div class="btn-row">
                <button type="submit" class="btn-primary">Save & Connect</button>
            </div>
        </form>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        if self.path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = urllib.parse.parse_qs(body)

            config.server_url = params.get("server_url", [""])[0].strip()
            config.client_api_key = params.get("client_api_key", [""])[0].strip()
            config.client_name = params.get("client_name", [""])[0].strip()
            config.save()

            relay_worker.trigger_reconnect()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Settings Saved!</h1><p>TinyPOS is reconnecting. You can close this tab.</p><script>setTimeout(() => window.close(), 2500);</script>")


def open_browser_settings():
    """Launch local web server fallback and open in browser."""
    def _run_server():
        try:
            with socketserver.TCPServer(("127.0.0.1", 0), WebConfigHandler) as httpd:
                port = httpd.server_address[1]
                logger.info(f"Opened web settings server on http://127.0.0.1:{port}")
                webbrowser.open(f"http://127.0.0.1:{port}")
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start fallback web settings server: {e}")

    threading.Thread(target=_run_server, daemon=True).start()
