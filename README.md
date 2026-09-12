# TinyPOS &bull; Thermal POS Bridge Application

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 📖 **Developer Integration Guide & API Reference**: For comprehensive REST API documentation, schemas, payloads, and code snippets in cURL, JavaScript, Python, and PHP, see **[DOC.md](DOC.md)**.

**TinyPOS** is a cross-platform, lightweight FastAPI bridge that connects web applications (Laravel, ERPNext, custom POS software) to local Bluetooth Low Energy (BLE) thermal receipt printers running the **Bainiu / Tiny Print** protocol (such as X6, X5, C9, iPrint, etc.).

It runs seamlessly on macOS, Linux, Raspberry Pi, and Windows, exposing both a modern Web Dashboard and a REST API with 1-step direct printing, mid-stream print cancellation, universal multi-language support, and auto-scaling for 80mm/A4 receipts.

---

## Key Features

- **100% Universal World Language & Emoji Support:** Print receipts in any living language on Earth — Bengali, Arabic, Urdu, English, Chinese, Hindi, Russian, Japanese, Telugu, Tamil, Korean, Thai, Gujarati, Kannada, Malayalam, Odia, Burmese, Punjabi, Ethiopic/Amharic, Lao, Khmer, Sinhala, Greek, Hebrew, Armenian, Georgian, and all Emojis — seamlessly mixed on the same line without missing glyph boxes.
- **Photographic Dithering & Shading Engine:** Dedicated photo processor (`engine/photo.py`) with Floyd-Steinberg error-diffusion dithering and thermal dot-gain dynamic range compensation, reproducing smooth skin tones and soft gradients matching the official Tiny Print app.
- **Direct 1-Step Printing:** Print formatted text, receipts, or PDF/image files immediately via REST API or the Web UI.
- **Direct QR Code Generation & Printing:** Print thermal QR codes directly, or generate/stream 384px PNG QR codes on-the-fly via `/api/qr/generate` for embedding in web `<img>` tags or reports.
- **Paper Feed & Cut Margin:** Advance paper roll on-demand via `/api/print/feed` to ensure clean receipt tearing.
- **Drag-and-Drop File Uploader:** Intuitive drag-and-drop dropzone on the web console with instant file size/type detection and auto-scaling to 384 dots.
- **Live Job Cancellation:** Stop and abort active print jobs mid-stream from the dashboard or API to prevent paper waste.
- **Receipt Auto-Scaling & Margin Cropping:** Automatically crop white borders and scale 80mm/A4 receipts to fit 57mm rolls cleanly.
- **Adjustable Print Darkness (1–7):** Fine-tune thermal burn strength for faint or aged paper rolls.
- **Cross-Platform & Zero Configuration:** Runs natively on macOS, Linux, Raspberry Pi, and Windows with bundled fonts included out-of-the-box.
- **Storage & Memory Protection:** Automatically purges temporary print jobs after 5 minutes to prevent database bloat.
- **Modern Web Dashboard:** Manage API keys, monitor recent jobs, test printer hardware with built-in language presets, and view interactive API docs.

---

## Directory Structure
```
TinyPOS/
├── DOC.md              # Complete Developer Integration Guide & REST API Specification
├── README.md           # Getting started, architecture, and deployment guide
├── .env                # Local configuration (ADMIN_USERNAME, ADMIN_PASSWORD, PORT, HOST)
├── .env.example        # Environment configuration template
├── .gitignore          # Rules for venv, caches, build artifacts, SQLite DBs, and logs
├── requirements.txt    # Server Python dependencies (FastAPI, uvicorn, bleak, Pillow, etc.)
├── main.py             # FastAPI entrypoint & background cleaner lifecycle
├── printer_ble.py      # Direct BLE printer connection & hardware transport driver
├── engine/             # Printing engine (text layout, fonts, protocol, bitmap rendering)
├── fonts/              # Cross-platform bundled fonts for universal script support
├── test_app.py         # Comprehensive automated test suite
├── tinypos.db          # SQLite database (auto-created on launch)
├── ecosystem.config.js # PM2 process manager configuration
├── server/             # Modular server core (auth, database, print service, routes)
├── UI/                 # Modern Web Dashboard (console, API keys, settings, docs)
│   ├── static/         # Brand assets & favicons (icon.png, favicon.ico)
│   └── documentation/  # Interactive web documentation subpages
└── client-app/         # Native Desktop Menu Bar / System Tray client for Cloud Relay
    ├── build.py        # Automated cross-platform standalone builder (macOS/Win/Linux)
    ├── packager.py     # Native installer generator (.dmg, Inno Setup .exe, .deb, .tar.gz)
    ├── run.sh          # Quick launch script for desktop client
    ├── requirements.txt# Client dependencies (bleak, websockets, Pillow, pyobjc/pystray)
    ├── main.py         # Client launcher & platform selector
    ├── icon/           # Squircle app icon assets (icon.icns, icon.ico, icon.png)
    ├── ui/             # Native settings GUIs (Cocoa, Qt6, Tkinter, Browser fallback)
    └── core/           # Tray UI, Bluetooth LE driver, and WebSocket relay worker
```

---

## Getting Started

### 1. Installation
```bash
# Clone the repository
git clone <repo_url>
cd TinyPOS

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration
cp .env.example .env
```

### 2. Configuration (`.env`)
Edit `.env` to set your desired port and credentials:
```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
PORT=8100
HOST=0.0.0.0
```

### 3. Running the Server

**Development Mode (Live Reloading):**
```bash
.venv/bin/python main.py
```
*or using Uvicorn directly:*
```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

**Production Mode with PM2:**
```bash
pm2 start ecosystem.config.js
pm2 logs tinypos
```

**Accessing the Dashboard:**
1. Open `http://localhost:8100` (or your server/tunnel domain).
2. Log in using your `.env` credentials.
3. Access the **Printer Test Console**, **API Keys**, and **Documentation**.

---

## REST API Reference

All requests to `/api/*` require authentication via the `X-API-Key` HTTP header (or `?api_key=` query parameter for direct browser media streams).

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/print/photo` | **Photo Studio Print:** High-fidelity 1-bit thermal halftoning for photos and artwork with quality presets (`portrait`, `sharp`, `balanced`, `high_contrast`, `halftone`). | `X-API-Key` |
| `POST` | `/api/print/raw` | **Upload & Print:** PDF or Image invoice document with auto-scaling, auto-cropping, and strength options. | `X-API-Key` |
| `POST` | `/api/print/text` | **Direct Text Print:** Formatted receipt text supporting all living languages and emojis with customizable font size and strength. | `X-API-Key` |
| `POST` | `/api/print/qr` | **Direct QR Code Print:** High-contrast thermal QR code with optional multilingual header and footer text. | `X-API-Key` |
| `GET` / `POST` | `/api/qr/generate` | **Direct QR Generator:** Directly streams a 384px PNG QR code from query parameters or JSON body (ideal for `<img>` tags). | `X-API-Key` or `?api_key=` |
| `POST` | `/api/print/feed` | **Paper Feed:** Advance/feed thermal paper roll (alias: `/api/printer/feed`). | `X-API-Key` |
| `POST` | `/api/print/stop` | **Immediate Stop:** Aborts whatever job is currently streaming to the thermal printer. | `X-API-Key` |
| `DELETE` / `POST` | `/api/print/cancel/{job_id}` | Cancels a pending job or aborts an active printing job by ID. | `X-API-Key` |
| `POST` | `/api/print/confirm/{job_id}` | Confirms a pending job (if submitted with `immediate=false`). | `X-API-Key` |
| `GET` | `/api/print/preview/{job_id}` | Returns a 384px monochrome PNG preview of the rasterized receipt. | `X-API-Key`, `?api_key=`, or Admin Session |
| `GET` | `/api/status` | Probes printer BLE connectivity and returns active transmission status (`is_printing`). | `X-API-Key` |
| `GET` | `/api/queue` | Returns paginated recent job history. | `X-API-Key` |
| `WebSocket` | `/ws/client` | **Cloud Relay Bridge:** Real-time bidirectional WebSocket stream for store client machines. | Client Key |

> 📖 **Developer Integration Guide & Multi-Language Code Examples:**
> For comprehensive REST API documentation, JSON request/response schemas, complete parameter explanations, and ready-to-use integration code examples in **cURL, JavaScript / TypeScript, Python, and PHP (Laravel)**, please see **[DOC.md](DOC.md)**.

---

## Dual Bridge Architecture

TinyPOS supports two distinct operational deployment modes:

```
MODE 1: Direct Local Bluetooth
┌─────────────────────────┐      Direct BLE      ┌───────────────────────┐
│ Web POS / Local Server  │ ───────────────────> │ Portable BLE Printer  │
└─────────────────────────┘                      └───────────────────────┘

MODE 2: Cloud Relay Mesh (Remote VPS Deployment)
┌─────────────────────────┐
│ Cloud Server (VPS)      │
│ e.g. your-pos-server.com│
└────────────┬────────────┘
             │  Bidirectional WebSocket (WSS)
             ▼
┌─────────────────────────┐      Local BLE       ┌───────────────────────┐
│ TinyPOS Desktop Client  │ ───────────────────> │ Portable BLE Printer  │
│ (Mac / Windows / Linux) │   Presence & RSSI    └───────────────────────┘
└─────────────────────────┘
```

1. **Direct Local Bluetooth Mode:** Used when the TinyPOS server runs directly on the local store machine (e.g. Raspberry Pi, Mac Mini, Windows POS terminal) that has Bluetooth hardware in physical range of the printer.
2. **Cloud Relay Mode:** Used when TinyPOS is hosted remotely on a VPS or cloud infrastructure (e.g. AWS, DigitalOcean, Ubuntu server) without local Bluetooth hardware:
   - Remote store PCs run the lightweight **TinyPOS Desktop Client** (`client-app/`).
   - Multiple store PCs can connect simultaneously across terminal groups.
   - The cloud relay automatically detects which terminal is closest to the printer via BLE RSSI signal strength and routes jobs without collisions.

---

## TinyPOS Desktop Client (`client-app/`)

The desktop client is a native Menu Bar / System Tray application designed to run quietly in the background on store computers, connecting local Bluetooth thermal receipt printers to the TinyPOS Cloud Relay.

### Key Capabilities

* **Native Menu Bar / System Tray Integration**:
  * **macOS**: Runs as a Dockless background status item in the top menu bar using Apple Cocoa (`NSStatusBar`, `NSMenu`, `LSUIElement`).
  * **Windows**: Runs in the bottom-right taskbar notification area via Win32. Right-click for context menu, left-click or double-click to open the Control Panel.
  * **Linux**: Runs in the system tray / panel using AppIndicator or Xorg XEmbed with single-click activation.
  * **Dynamic Status Badges**:
    * 🟢 **Green**: Connected to Cloud Relay & Bluetooth Printer Online and Ready.
    * 🟡 **Yellow**: Connected to Cloud Relay, but Printer is Offline or Out of Bluetooth Range.
    * 🔴 **Red**: Disconnected from Cloud Relay / Reconnecting.
    * ⚪ **Gray**: Unconfigured.
* **Universal Control Panel & Settings GUI**:
  * Clean, native settings window available across all platforms (Cocoa on macOS, Qt6/Tkinter on Windows/Linux, with an automatic zero-dependency local browser fallback if GUI toolkits are unavailable).
  * Automatically pops up on first launch when unconfigured.
  * Live status overview (Cloud Relay connection state, Terminal Group, Printer model & Bluetooth RSSI).
  * In-window hardware actions: **Feed Paper**, **Reconnect Now**, and **Test Connection**.
* **1-Click Quick Setup (URL Auto-Parser)**:
  * Simply paste the full WebSocket connection URL generated from your TinyPOS server's **Settings** page (e.g. `wss://your-pos-server.com/ws/client?api_key=...`), and the app automatically parses the Server URL, Client API Key, and Terminal Name!
* **Smart Roaming & Heartbeats**:
  * Continuously scans for your portable Bluetooth printer in the background with 4-scan debouncing and a 25-second post-print grace period.
  * Reports signal strength (RSSI dBm) and presence to the cloud relay.
  * Whichever computer detects the printer automatically becomes the active print target.
* **Paper Feed Action**:
  * Easily test or feed thermal paper directly from the menu bar item or the settings window.
* **Single-Instance Protection**:
  * Uses a dedicated loopback socket lock (`127.0.0.1:49281`) to prevent multiple duplicate instances from opening simultaneously.

---

### Supported Thermal Printers

* **Bainiu / Tiny Print 57mm BLE Printers**: X6, X5, C9, MX0, iPrint, GB01, and compatible pocket thermal printers.
* **Standard ESC/POS Bluetooth Low Energy Printers**: Any BLE thermal printer exposing standard service UUIDs `0xAE30`, `0xAF30`, or `0xFF00`.

---

### Quick Start & Configuration

#### 1. Launching the Client

From the project root:

```bash
./client-app/run.sh
```

Or using Python directly:

```bash
python3 client-app/main.py
```

#### 2. Configuring the Connection

On first launch, the **Settings & Control Panel** window opens automatically:

1. **Option A (1-Click Quick Setup)**:
   * Open your TinyPOS web dashboard (e.g. `https://your-pos-server.com/settings`).
   * In the **Client Terminal Authorization Keys** table, click the copy button next to your terminal's **WebSocket Connection URL**.
   * Paste the URL into the **Quick Connect** box in the client app and click **Paste & Apply**.
2. **Option B (Manual Setup)**:
   * **Cloud Server URL**: e.g. `wss://your-pos-server.com`
   * **Client API Key**: e.g. `sk_client_cmi9ort2mxog5jkjnr2c2lo4`
   * **Terminal Name**: e.g. `Mac Mini` or `Windows-POS`
3. Click **🧪 Test Connection** to verify WebSocket handshake and group authorization.
4. Click **💾 Save & Connect**.

---

### Packaging Standalone Executables & Native Installers

TinyPOS can be compiled into portable, standalone applications and native operating system release installers without requiring Python on target client computers:

#### 1. Compile Standalone Application Bundles (`build.py`)

```bash
cd client-app
python3 build.py
```

| Platform | Output Artifact | Build Details |
|---|---|---|
| **macOS** | `dist/TinyPOS.app` | Native Cocoa Menu Bar Agent (`LSUIElement`), Retina squircle icon (`icon.icns`), Bluetooth privacy permissions, ad-hoc codesigned. Strip-optimized for Darwin. |
| **Windows** | `dist/TinyPOS/` | Optimized `--onedir` bundle with Qt6/Tkinter settings GUI, embedded multi-resolution icon (`icon.ico`), Win32 tray notification area hooks, and crash recovery. |
| **Linux** | `dist/TinyPOS` | Standalone ELF binary with embedded `icon.png` and AppIndicator/XEmbed panel integration. |

#### 2. Generate Release Installers (`packager.py`)

Package the compiled standalone application into production-ready release installers for end users:

```bash
cd client-app
python3 packager.py
```

| Platform | Installer Package | Format | Details |
|---|---|---|---|
| **macOS** | `dist/installer/TinyPOS-1.0.0-macOS.dmg` | **Apple Disk Image** | Drag-and-drop installer with customized volume layout and `/Applications` alias symlink. |
| **Windows** | `dist/installer/TinyPOS-Setup-1.0.0.exe` | **Inno Setup 6/7 Installer** | Ultra-compressed wizard installer using LZMA2 solid compression. Includes Start Menu shortcuts, desktop shortcut, clean uninstaller, and single-instance kill guard. |
| **Linux** | `dist/installer/tinypos_1.0.0_amd64.deb`<br>`TinyPOS-1.0.0-linux-x86_64.tar.gz` | **Debian Package & Archive** | Standard Debian package installing to `/opt/tinypos` with desktop `.desktop` entry, icon integration, and terminal symlink `/usr/local/bin/tinypos`. |

*Note: All intermediate build caches (`build/`, `.spec` files, `__pycache__`) are automatically pruned immediately upon build completion.*

---

## Running Verification Tests
TinyPOS includes an automated end-to-end test suite covering SQLite CRUD, Authentication, 1-Step Printing, Temporary Job Cleanup, Stop/Cancel APIs, and Universal Multi-Language Text Rendering:

```bash
.venv/bin/python test_app.py
```

---

## License
MIT License. Free for commercial and personal POS deployments.
