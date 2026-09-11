# TinyPOS Desktop Client

A lightweight, native Menu Bar / System Tray application that connects your local Bluetooth thermal printer (X6, Bainiu, Tiny Print) to the TinyPOS Cloud Relay.

---

## Features

* **Native Menu Bar / System Tray Integration**:
  * Runs quietly in your macOS top menu bar or Windows/Linux system tray.
  * **Dynamic Status Badges**:
    * 🟢 **Green**: Connected to Cloud Relay & Bluetooth Printer Online.
    * 🟡 **Yellow**: Connected to Cloud Relay, but Printer is Offline or Out of Range.
    * 🔴 **Red**: Disconnected from Cloud Relay / Reconnecting.
    * ⚪ **Gray**: Unconfigured.
* **Quick 1-Click Setup**:
  * Simply paste the full WebSocket connection URL generated from your TinyPOS server's **Settings** page (e.g. `wss://pos.sayem.top/ws/client?api_key=...`), and the app automatically parses the Server URL, Client API Key, and Terminal Name!
* **Smart Roaming & Heartbeats**:
  * Continuously scans for your portable Bluetooth printer in the background.
  * Reports signal strength (RSSI dBm) and presence to the cloud relay.
  * Whichever computer detects the printer automatically becomes the active print target.
* **Paper Feed Action**:
  * Easily test or feed thermal paper directly from the menu bar item.

---

## Quick Start

### 1. Launch the Application

From the project root:

```bash
./client-app/run.sh
```

Or using Python directly:

```bash
python3 client-app/main.py
```

### 2. Configure the Connection

On first launch, the **Settings** window will open automatically.

1. **Option A (Quick Setup)**:
   * Open your TinyPOS web dashboard (e.g. `https://pos.sayem.top/settings`).
   * In the **Client Terminal Authorization Keys** table, click the copy button next to the **WebSocket Connection URL** for your terminal.
   * Paste the URL into the **Quick Setup** box in the client app and click **Auto-Fill**.
2. **Option B (Manual Setup)**:
   * **Cloud Server URL**: e.g. `https://pos.sayem.top`
   * **Client API Key**: e.g. `sk_client_cmi9ort2mxog5jkjnr2c2lo4`
   * **Terminal Name**: e.g. `Mac Mini`
3. Click **Test Connection** to verify.
4. Click **Save & Connect**.

---

## Supported Printers

* Bainiu / Tiny Print 57mm BLE thermal printers (X6, X5, GB01, MX0, iPrint, etc.)
* Any ESC/POS Bluetooth Low Energy printer using service UUIDs `0xAE30`, `0xAF30`, or `0xFF00`.
