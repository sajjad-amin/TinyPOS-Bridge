"""
TinyPOS WebSocket Cloud Relay Manager (Multi-Terminal & Roaming Presence Mesh)
Maintains persistent WebSocket connections with multiple store client machines simultaneously.
Automatically discovers which terminal is closest to the portable thermal printer via BLE presence/RSSI
and dispatches print jobs without duplicate prints or conflicts.
"""

import asyncio
import base64
import datetime
import io
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from fastapi import WebSocket
from PIL import Image

logger = logging.getLogger("tinypos.relay")


class RelayManager:
    def __init__(self):
        # Maps client_id -> client_data dict
        self._clients: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._pending_jobs: Dict[str, asyncio.Future] = {}
        self._active_job_id: Optional[str] = None
        self._is_printing: bool = False

    def is_any_client_connected(self) -> bool:
        """Return True if at least one remote store terminal is connected."""
        return len(self._clients) > 0

    def is_client_connected(self) -> bool:
        """Alias for is_any_client_connected for backward compatibility."""
        return self.is_any_client_connected()

    def get_client_count(self) -> int:
        """Return the number of connected store terminals."""
        return len(self._clients)

    def is_printing(self) -> bool:
        """Check whether a relay print job is actively in progress."""
        return self._is_printing

    def get_active_job_id(self) -> Optional[str]:
        """Return the currently executing relay job ID if any."""
        return self._active_job_id

    @staticmethod
    def _sanitize_client(c: Optional[Dict[str, Any]], is_active: bool = False) -> Optional[Dict[str, Any]]:
        """Return a clean JSON-serializable dictionary without WebSocket objects."""
        if not c:
            return None
        return {
            "client_id": c.get("client_id"),
            "client_name": c.get("client_name", "Terminal"),
            "ip": c.get("ip", "unknown"),
            "api_key": c.get("api_key", ""),
            "connected_at": c.get("connected_at", ""),
            "last_ping": c.get("last_ping", ""),
            "printer_online": bool(c.get("printer_online", False)),
            "printer_name": c.get("printer_name"),
            "printer_address": c.get("printer_address"),
            "rssi": c.get("rssi"),
            "is_active_target": is_active,
            "printer_status": {
                "status": "online" if c.get("printer_online") else "offline",
                "device_name": c.get("printer_name"),
                "address": c.get("printer_address"),
                "rssi": c.get("rssi"),
            },
        }

    def _get_raw_active_client(self) -> Optional[Dict[str, Any]]:
        """Internal resolver: returns raw client dict including ws object."""
        candidates = [c for c in self._clients.values() if c.get("printer_online")]
        if not candidates:
            return None

        def sort_key(c):
            rssi = c.get("rssi")
            rssi_val = rssi if (isinstance(rssi, (int, float)) and rssi != 0) else -999
            return (rssi_val, c.get("last_ping", ""))

        sorted_candidates = sorted(candidates, key=sort_key, reverse=True)
        return sorted_candidates[0]

    def get_active_printing_client(self) -> Optional[Dict[str, Any]]:
        """
        Roaming Resolver: Finds the client terminal that currently has the portable
        printer in Bluetooth range. If multiple PCs see the printer (e.g. in the same room),
        selects the one with the strongest signal strength (highest RSSI / closest proximity).
        Returns a sanitized JSON-serializable dictionary.
        """
        raw = self._get_raw_active_client()
        return self._sanitize_client(raw, is_active=True)

    def is_printer_available(self) -> bool:
        """Check if any connected terminal currently detects the thermal printer online."""
        return self._get_raw_active_client() is not None

    def get_connected_clients_summary(self) -> List[Dict[str, Any]]:
        """
        Return a JSON-serializable list of all connected terminals, marking
        the one currently designated as the active roaming target.
        """
        raw_target = self._get_raw_active_client()
        active_id = raw_target.get("client_id") if raw_target else None

        results = []
        for cid, c in self._clients.items():
            results.append(self._sanitize_client(c, is_active=(cid == active_id)))
        return results

    def get_client_info(self) -> Optional[Dict[str, Any]]:
        """
        Backward compatibility: returns the active roaming terminal's metadata,
        or the first connected terminal if none currently has printer online.
        """
        raw = self._get_raw_active_client()
        if raw:
            return {
                "client_id": raw.get("client_id"),
                "client_name": raw.get("client_name"),
                "ip": raw.get("ip"),
                "connected_at": raw.get("connected_at"),
                "last_ping": raw.get("last_ping"),
                "printer_status": {
                    "status": "online" if raw.get("printer_online") else "offline",
                    "device_name": raw.get("printer_name"),
                    "address": raw.get("printer_address"),
                    "rssi": raw.get("rssi"),
                },
                "is_active_target": True,
            }
        if self._clients:
            first = next(iter(self._clients.values()))
            return {
                "client_id": first.get("client_id"),
                "client_name": first.get("client_name"),
                "ip": first.get("ip"),
                "connected_at": first.get("connected_at"),
                "last_ping": first.get("last_ping"),
                "printer_status": {
                    "status": "offline",
                    "device_name": None,
                    "address": None,
                    "rssi": None,
                },
                "is_active_target": False,
            }
        return None

    def get_connected_api_keys(self) -> Dict[str, Dict[str, Any]]:
        """Return a mapping of api_key -> client_summary for all currently connected terminals."""
        active = self.get_active_printing_client()
        active_id = active.get("client_id") if active else None
        res = {}
        for c in self._clients.values():
            k = c.get("api_key")
            if k:
                res[k] = self._sanitize_client(c, is_active=(c.get("client_id") == active_id))
        return res

    async def disconnect_by_api_key(self, api_key: str):
        """Forcefully disconnect any active WebSocket terminal using the specified API key."""
        clean_key = (api_key or "").strip()
        if not clean_key:
            return
        async with self._lock:
            to_remove = [c for c in self._clients.values() if c.get("api_key") == clean_key]
            for c in to_remove:
                ws = c.get("ws")
                if ws:
                    try:
                        await ws.close(code=1008, reason="API Key revoked by administrator")
                    except Exception:
                        pass
                cid = c.get("client_id")
                if cid in self._clients:
                    self._clients.pop(cid, None)
                    logger.info(f"Terminated client '{c.get('client_name')}' because API key was deleted.")

    async def register(
        self,
        websocket: WebSocket,
        client_name: str = "Store Terminal",
        client_ip: str = "unknown",
        api_key: str = "",
        key_name: str = "",
        client_id: Optional[str] = None,
    ) -> str:
        """Register a new active client terminal WebSocket connection."""
        async with self._lock:
            cid = client_id or str(uuid.uuid4())[:8]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            self._clients[cid] = {
                "client_id": cid,
                "client_name": client_name,
                "key_name": key_name or client_name,
                "ip": client_ip,
                "api_key": api_key,
                "ws": websocket,
                "connected_at": now_iso,
                "last_ping": now_iso,
                "printer_online": False,
                "printer_name": None,
                "printer_address": None,
                "rssi": None,
            }
            logger.info(f"Relay client registered: '{client_name}' (Key: {key_name}, ID: {cid}) from {client_ip} [Total: {len(self._clients)}]")
            return cid

    async def unregister(self, websocket: WebSocket):
        """Unregister a disconnected terminal WebSocket connection."""
        async with self._lock:
            target_cid = None
            for cid, c in list(self._clients.items()):
                if c.get("ws") == websocket:
                    target_cid = cid
                    break

            if target_cid:
                c = self._clients.pop(target_cid)
                logger.info(f"Relay client disconnected: '{c.get('client_name')}' (ID: {target_cid}) [Remaining: {len(self._clients)}]")

                # If no clients remain, cancel any pending jobs
                if not self._clients:
                    for job_id, fut in list(self._pending_jobs.items()):
                        if not fut.done():
                            fut.set_result((False, "All store terminals disconnected while executing print job."))
                    self._pending_jobs.clear()
                    self._is_printing = False
                    self._active_job_id = None

    async def handle_client_message(self, websocket: WebSocket, data: Dict[str, Any]):
        """Process incoming WebSocket messages from a client terminal."""
        # Locate client record
        client = None
        for c in self._clients.values():
            if c.get("ws") == websocket:
                client = c
                break

        if not client:
            return

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        client["last_ping"] = now_iso

        msg_type = data.get("type", "").lower()

        if msg_type in ("ping", "heartbeat"):
            # Update telemetry if bundled in heartbeat
            if "printer_online" in data or "status" in data:
                is_on = bool(data.get("printer_online", False)) or (str(data.get("status", "")).lower() in ("online", "connected", "ready"))
                client["printer_online"] = is_on
                if "printer_name" in data or "device_name" in data:
                    client["printer_name"] = data.get("printer_name") or data.get("device_name")
                if "address" in data:
                    client["printer_address"] = data.get("address")
                if "rssi" in data:
                    client["rssi"] = data.get("rssi")

            try:
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": now_iso,
                    "is_active_target": (self.get_active_printing_client() == client),
                })
            except Exception:
                pass

        elif msg_type == "printer_status":
            # Client reporting local thermal printer presence
            status_str = str(data.get("status", "")).lower()
            is_online = status_str in ("online", "connected", "ready", "true")
            client["printer_online"] = is_online
            client["printer_name"] = data.get("printer_name") or data.get("device_name")
            client["printer_address"] = data.get("address")
            client["rssi"] = data.get("rssi")
            logger.info(
                f"Terminal '{client['client_name']}' presence update: printer_online={is_online}, "
                f"device='{client['printer_name']}', rssi={client['rssi']} dBm"
            )

        elif msg_type == "job_ack":
            job_id = data.get("job_id")
            logger.info(f"Terminal '{client['client_name']}' acknowledged job {job_id}")

        elif msg_type == "job_completed":
            job_id = data.get("job_id")
            logger.info(f"Terminal '{client['client_name']}' completed job {job_id}")
            fut = self._pending_jobs.get(job_id)
            if fut and not fut.done():
                fut.set_result((True, data.get("message", f"Printed successfully via {client['client_name']}.")))

        elif msg_type == "job_failed":
            job_id = data.get("job_id")
            error = data.get("error", "Terminal reported print failure.")
            logger.warning(f"Terminal '{client['client_name']}' failed job {job_id}: {error}")
            fut = self._pending_jobs.get(job_id)
            if fut and not fut.done():
                fut.set_result((False, f"Terminal {client['client_name']} error: {error}"))

    async def dispatch_job_to_client(
        self,
        job_id: str,
        img: Image.Image,
        strength: int = 7,
        timeout: float = 60.0,
        preferred_client_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Smart Roaming Dispatcher:
        Resolves which connected terminal currently has the portable thermal printer
        in Bluetooth range and transmits the print job strictly to that terminal.
        """
        if not self.is_any_client_connected():
            return (
                False,
                "Cloud Relay mode is active, but no store terminals are currently connected. "
                "Please run TinyPOS client software on your store machine.",
            )

        # Select destination terminal
        target = None
        if preferred_client_id and preferred_client_id in self._clients:
            target = self._clients[preferred_client_id]
        else:
            target = self.get_active_printing_client()

        if not target:
            client_count = len(self._clients)
            names = ", ".join(c.get("client_name", "Terminal") for c in self._clients.values())
            return (
                False,
                f"Cloud Relay: {client_count} terminal(s) connected ({names}), but your portable printer is currently turned off or out of Bluetooth range."
            )

        target_ws: WebSocket = target["ws"]
        target_name = target.get("client_name", "Store Terminal")

        # Convert image to Base64 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_jobs[job_id] = future
        self._is_printing = True
        self._active_job_id = job_id

        payload = {
            "type": "print_job",
            "job_id": job_id,
            "image_b64": b64_data,
            "width": img.width,
            "height": img.height,
            "strength": strength,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        try:
            await target_ws.send_json(payload)
            logger.info(
                f"Dispatched job {job_id} to roaming target terminal '{target_name}' "
                f"(RSSI: {target.get('rssi')} dBm, size: {img.width}x{img.height}). Awaiting response..."
            )

            success, message = await asyncio.wait_for(future, timeout=timeout)
            return success, message

        except asyncio.TimeoutError:
            logger.error(f"Relay job {job_id} on terminal '{target_name}' timed out after {timeout} seconds.")
            return False, f"Print job timed out after {int(timeout)}s waiting for terminal '{target_name}' printer response."

        except Exception as e:
            logger.error(f"Exception dispatching job {job_id} to terminal '{target_name}': {e}")
            return False, f"Failed to transmit print job to terminal '{target_name}': {str(e)}"

        finally:
            self._pending_jobs.pop(job_id, None)
            self._is_printing = False
            self._active_job_id = None

    async def stop_active_job(self) -> Tuple[bool, str]:
        """Instruct the active printing terminal to stop transmission."""
        if not self._is_printing or not self._active_job_id:
            return False, "No active relay print job is running."

        active_id = self._active_job_id
        # Broadcast stop command to all connected terminals
        for c in self._clients.values():
            try:
                await c["ws"].send_json({"type": "stop_job", "job_id": active_id})
            except Exception:
                pass

        fut = self._pending_jobs.get(active_id)
        if fut and not fut.done():
            fut.set_result((False, "Print job stopped by user command."))

        self._is_printing = False
        self._active_job_id = None
        return True, "Stop command dispatched to terminals."

    async def feed_paper(self) -> Tuple[bool, str]:
        """Send feed paper command through active roaming terminal."""
        target = self.get_active_printing_client()
        if not target:
            return False, "No active terminal with thermal printer online."

        try:
            await target["ws"].send_json({"type": "feed_paper"})
            return True, f"Feed paper command sent to {target.get('client_name')}."
        except Exception as e:
            return False, str(e)


# App-wide singleton
relay_manager = RelayManager()
