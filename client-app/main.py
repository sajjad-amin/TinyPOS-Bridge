#!/usr/bin/env python3
"""
TinyPOS Desktop Client Application
Menu Bar / System Tray Bridge for Bluetooth Thermal Printers.
"""

import logging
import sys
from pathlib import Path

# Ensure client-app directory is in python path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("tinypos.client")


def main():
    logger.info("Initializing TinyPOS Desktop Client...")

    if sys.platform == "darwin":
        from core.tray_mac import run_mac_app
        run_mac_app()
    else:
        from core.tray_crossplatform import run_crossplatform_app
        run_crossplatform_app()


if __name__ == "__main__":
    main()
