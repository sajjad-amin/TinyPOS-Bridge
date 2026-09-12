"""
Configuration Manager for TinyPOS Client Application
Handles persistence to ~/.tinypos_client/config.json and URL parsing.
"""

import json
import os
import platform
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_DIR = Path.home() / ".tinypos_client"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_default_client_name() -> str:
    """Generate a sensible default terminal name based on the machine's hostname."""
    name = platform.node() or "Store Terminal"
    # Remove .local or domain suffix if present
    return name.split(".")[0]


class ClientConfig:
    def __init__(self):
        self.server_url: str = ""
        self.client_api_key: str = ""
        self.client_name: str = get_default_client_name()
        self.printer_address: str = ""
        self.printer_name: str = ""
        self.auto_connect: bool = True
        self.load()

    def is_configured(self) -> bool:
        """Check if the minimum required settings (Server URL and API Key) are present."""
        return bool(self.server_url.strip() and self.client_api_key.strip())

    def load(self):
        """Load configuration from disk if available."""
        if not CONFIG_FILE.exists():
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.server_url = (data.get("server_url") or "").strip()
                self.client_api_key = (data.get("client_api_key") or "").strip()
                self.client_name = (data.get("client_name") or get_default_client_name()).strip()
                self.printer_address = (data.get("printer_address") or "").strip()
                self.printer_name = (data.get("printer_name") or "").strip()
                self.auto_connect = bool(data.get("auto_connect", True))
        except Exception as e:
            print(f"[Config] Error loading {CONFIG_FILE}: {e}")

    def save(self):
        """Persist current configuration to ~/.tinypos_client/config.json."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "server_url": self.server_url.strip(),
                "client_api_key": self.client_api_key.strip(),
                "client_name": self.client_name.strip() or get_default_client_name(),
                "printer_address": self.printer_address.strip(),
                "printer_name": self.printer_name.strip(),
                "auto_connect": self.auto_connect,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving {CONFIG_FILE}: {e}")

    def delete(self):
        """Remove configuration file from disk and clear in-memory credentials."""
        self.server_url = ""
        self.client_api_key = ""
        self.client_name = get_default_client_name()
        self.printer_address = ""
        self.printer_name = ""
        self.auto_connect = True
        try:
            if CONFIG_FILE.exists():
                CONFIG_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Config] Error deleting {CONFIG_FILE}: {e}")

    @staticmethod
    def parse_ws_url(raw_url: str) -> Dict[str, str]:
        """
        Parses a full WebSocket connection URL or standard web URL.
        Example:
            wss://pos.sayem.top/ws/client?api_key=sk_client_cmi9ort2mxog5jkjnr2c2lo4&client_name=Mac_Mini
        Returns:
            {
                "server_url": "wss://pos.sayem.top",
                "client_api_key": "sk_client_cmi9ort2mxog5jkjnr2c2lo4",
                "client_name": "Mac_Mini"
            }
        """
        clean = (raw_url or "").strip()
        if not clean:
            return {}

        parsed = urllib.parse.urlparse(clean)
        scheme = parsed.scheme.lower()
        if not scheme:
            # If user entered pos.sayem.top without scheme, assume wss
            clean = "wss://" + clean
            parsed = urllib.parse.urlparse(clean)
            scheme = parsed.scheme.lower()

        # Extract base server URL (scheme + netloc)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Extract query parameters
        query_params = urllib.parse.parse_qs(parsed.query)
        api_key = ""
        if "api_key" in query_params and query_params["api_key"]:
            api_key = query_params["api_key"][0].strip()

        client_name = ""
        if "client_name" in query_params and query_params["client_name"]:
            client_name = query_params["client_name"][0].strip()

        return {
            "server_url": base_url,
            "client_api_key": api_key,
            "client_name": client_name,
        }

    def get_full_ws_url(self) -> Optional[str]:
        """
        Constructs the final WebSocket URL for connecting to the TinyPOS Cloud Relay.
        Converts http:// -> ws:// and https:// -> wss://.
        """
        if not self.server_url.strip() or not self.client_api_key.strip():
            return None

        clean_url = self.server_url.strip()
        parsed = urllib.parse.urlparse(clean_url)
        scheme = parsed.scheme.lower()

        if scheme in ("http", "ws"):
            ws_scheme = "ws"
        else:
            ws_scheme = "wss"

        netloc = parsed.netloc or parsed.path.split("/")[0]

        query = urllib.parse.urlencode({
            "api_key": self.client_api_key.strip(),
            "client_name": self.client_name.strip() or get_default_client_name(),
        })

        return f"{ws_scheme}://{netloc}/ws/client?{query}"


config = ClientConfig()
