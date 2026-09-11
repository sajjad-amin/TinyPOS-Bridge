"""
TinyPOS Client Relay Worker
Manages persistent WebSocket connection to the Cloud Relay, heartbeat reporting,
and automated execution of incoming print jobs.
"""

import asyncio
import base64
import io
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional
from PIL import Image
import websockets

from .config import config
from .ble_driver import ble_driver

logger = logging.getLogger("tinypos.client.relay")


class RelayWorker:
    def __init__(self):
        self.is_running: bool = False
        self.is_connected: bool = False
        self.current_group: Optional[str] = None
        self.last_status_message: str = "Ready"
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._force_reconnect: bool = False

    def set_status_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register a callback to notify the GUI of connection & printer state changes."""
        self._status_callback = callback

    def _notify(self, state: str, extra: Optional[Dict[str, Any]] = None):
        if self._status_callback:
            info = {
                "state": state,
                "is_connected": self.is_connected,
                "group": self.current_group,
                "printer_online": ble_driver.is_online,
                "printer_name": ble_driver.device_name,
                "rssi": ble_driver.rssi,
                "message": self.last_status_message,
            }
            if extra:
                info.update(extra)
            try:
                self._status_callback(state, info)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def start(self):
        """Start the background relay worker thread."""
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._thread_entry, daemon=True, name="RelayWorkerThread")
        self._thread.start()

    def stop(self):
        """Gracefully stop the background worker."""
        self.is_running = False
        if self._loop and self._loop.is_running():
            for task in asyncio.all_tasks(self._loop):
                self._loop.call_soon_threadsafe(task.cancel)

    def trigger_reconnect(self):
        """Signals the loop to close the current connection and reconnect immediately."""
        self._force_reconnect = True
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)

    def feed_paper(self):
        """Thread-safely schedule paper feed on the relay worker's event loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._do_feed_paper(), self._loop)
        else:
            logger.warning("Relay worker loop is not running; cannot feed paper.")

    async def _do_feed_paper(self):
        """Execute manual paper feed via ble_driver."""
        logger.info("Executing manual paper feed command...")
        success, msg = await ble_driver.feed_paper()
        logger.info(f"Manual paper feed result: success={success}, msg={msg}")
        if self.is_connected and self._ws:
            await self._send_printer_status()
        self._notify("status_update")

    def _thread_entry(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_task())
        except (asyncio.CancelledError, RuntimeError):
            pass
        except Exception as e:
            logger.error(f"Relay worker loop crashed: {e}")
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self._loop.close()

    async def _main_task(self):
        try:
            ble_task = asyncio.create_task(self._ble_monitor_loop())
            ws_task = asyncio.create_task(self._ws_manager_loop())
            await asyncio.gather(ble_task, ws_task)
        except asyncio.CancelledError:
            pass

    async def _ble_monitor_loop(self):
        """Continuously monitors local Bluetooth for printer presence."""
        while self.is_running:
            prev_online = ble_driver.is_online
            await ble_driver.scan_printer(timeout=3.5)

            # If printer online state changed, notify server immediately
            if ble_driver.is_online != prev_online and self.is_connected and self._ws:
                await self._send_printer_status()

            self._notify("status_update")
            await asyncio.sleep(4.0)

    async def _send_printer_status(self):
        """Transmit current Bluetooth printer status to cloud relay."""
        if not self._ws:
            return
        try:
            payload = {
                "type": "printer_status",
                "status": "online" if ble_driver.is_online else "offline",
                "printer_online": ble_driver.is_online,
                "printer_name": ble_driver.device_name or "X6 Thermal",
                "address": ble_driver.device_address or "",
                "rssi": ble_driver.rssi,
            }
            await self._ws.send(json.dumps(payload))
            logger.info(f"Reported printer status to cloud: {payload['status']} ({ble_driver.rssi} dBm)")
        except Exception as e:
            logger.debug(f"Failed to send printer status: {e}")

    async def _ws_manager_loop(self):
        """Manages WebSocket connection, message handling, and auto-reconnect."""
        backoff = 1.0

        while self.is_running:
            if not config.is_configured():
                self.is_connected = False
                self.last_status_message = "Configuration Required"
                self._notify("unconfigured")
                await asyncio.sleep(2.0)
                continue

            ws_url = config.get_full_ws_url()
            if not ws_url:
                await asyncio.sleep(2.0)
                continue

            self._force_reconnect = False
            self.last_status_message = "Connecting to Relay..."
            self._notify("connecting")

            try:
                logger.info(f"Connecting to WebSocket relay: {config.server_url} as '{config.client_name}'...")
                async with websockets.connect(
                    ws_url,
                    ping_interval=30,
                    ping_timeout=25,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self.is_connected = True
                    backoff = 1.0
                    self.last_status_message = "Connected"
                    logger.info("Connected to Cloud Relay successfully!")
                    self._notify("connected")

                    # Send initial printer status right after connect
                    await self._send_printer_status()

                    # Message processing loop
                    async for message in ws:
                        if self._force_reconnect:
                            break
                        await self._handle_server_message(message)

            except websockets.exceptions.InvalidStatusCode as e:
                self.is_connected = False
                if e.status_code == 403:
                    self.last_status_message = "Unauthorized (Invalid Client API Key)"
                    logger.error("Relay rejected connection: 403 Forbidden. Check Client API Key.")
                else:
                    self.last_status_message = f"HTTP Error {e.status_code}"
                self._notify("error", {"error": self.last_status_message})
                backoff = min(backoff * 1.5, 30.0)

            except Exception as e:
                self.is_connected = False
                self.last_status_message = f"Connection Lost ({type(e).__name__})"
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in {int(backoff)}s...")
                self._notify("disconnected")
                backoff = min(backoff * 1.5, 20.0)

            finally:
                self.is_connected = False
                self._ws = None

            if self.is_running:
                await asyncio.sleep(backoff)

    async def _handle_server_message(self, raw_msg: str):
        try:
            data = json.loads(raw_msg)
        except Exception:
            logger.warning(f"Received non-JSON message from relay: {raw_msg}")
            return

        msg_type = data.get("type", "").lower()

        if msg_type == "welcome":
            self.current_group = data.get("group")
            client_name = data.get("client_name")
            self.last_status_message = f"Active in Group: {self.current_group or 'Default'}"
            logger.info(f"Authenticated as '{client_name}' (Assigned Group: '{self.current_group}')")
            self._notify("authenticated")
            # Follow up with latest printer status
            await self._send_printer_status()

        elif msg_type == "ping":
            await self._ws.send(json.dumps({"type": "pong", "timestamp": time.time()}))

        elif msg_type == "print_job":
            job_id = data.get("job_id", "unknown")
            strength = int(data.get("strength", 7))
            b64_img = data.get("image_b64", "")

            logger.info(f"Received print job {job_id} (strength={strength}). Printing...")
            self._notify("printing", {"job_id": job_id})

            # Acknowledge receipt
            await self._ws.send(json.dumps({"type": "job_ack", "job_id": job_id}))

            # Decode Base64 PNG image
            try:
                raw_bytes = base64.b64decode(b64_img)
                img = Image.open(io.BytesIO(raw_bytes))

                # Stream to local Bluetooth printer
                success, msg = await ble_driver.print_bitmap(img, strength=strength)
                if success:
                    logger.info(f"Print job {job_id} succeeded!")
                    await self._ws.send(json.dumps({
                        "type": "job_completed",
                        "job_id": job_id,
                        "message": f"Printed successfully via {config.client_name}",
                    }))
                else:
                    logger.warning(f"Print job {job_id} failed: {msg}")
                    await self._ws.send(json.dumps({
                        "type": "job_failed",
                        "job_id": job_id,
                        "error": msg,
                    }))
            except Exception as e:
                logger.error(f"Error executing print job {job_id}: {e}")
                await self._ws.send(json.dumps({
                    "type": "job_failed",
                    "job_id": job_id,
                    "error": f"Client decoding error: {e}",
                }))
            finally:
                self._notify("status_update")

        elif msg_type == "feed_paper":
            logger.info("Received feed_paper command from relay...")
            success, msg = await ble_driver.feed_paper()
            if self._ws:
                await self._ws.send(json.dumps({
                    "type": "feed_paper_result",
                    "success": success,
                    "message": msg,
                }))
                await self._send_printer_status()
            self._notify("status_update")


relay_worker = RelayWorker()
