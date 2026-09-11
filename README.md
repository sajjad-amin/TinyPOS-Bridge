# TinyPOS &bull; Thermal POS Bridge Application

**TinyPOS** is a cross-platform, lightweight FastAPI bridge that connects web applications (Laravel, ERPNext, custom POS software) to local Bluetooth Low Energy (BLE) thermal receipt printers running the **Bainiu / Tiny Print** protocol (such as X6, X5, C9, iPrint, etc.).

It runs seamlessly on macOS, Linux, Raspberry Pi, and Windows, exposing both a modern Web Dashboard and a REST API with 1-step direct printing, mid-stream print cancellation, universal multi-language support, and auto-scaling for 80mm/A4 receipts.

---

## Key Features

- **100% Universal World Language & Emoji Support:** Print receipts in any living language on Earth — Bengali, Arabic, Urdu, English, Chinese, Hindi, Russian, Japanese, Telugu, Tamil, Korean, Thai, Gujarati, Kannada, Malayalam, Odia, Burmese, Punjabi, Ethiopic/Amharic, Lao, Khmer, Sinhala, Greek, Hebrew, Armenian, Georgian, and all Emojis — seamlessly mixed on the same line without missing glyph boxes.
- **Photographic Dithering & Shading Engine:** Dedicated photo processor (`engine/photo.py`) with Floyd-Steinberg error-diffusion dithering and thermal dot-gain dynamic range compensation, reproducing smooth skin tones and soft gradients matching the official Tiny Print app.
- **Direct 1-Step Printing:** Print formatted text, receipts, or PDF/image files immediately via REST API or the Web UI.
- **Direct QR Code Generation & Printing:** Print thermal QR codes directly, or generate/stream 384px PNG QR codes on-the-fly via `/api/qr/generate` for embedding in web `<img>` tags or reports.
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
└── client-app/         # Native Desktop Menu Bar / System Tray client for Cloud Relay
    ├── build.py        # Automated cross-platform standalone builder (macOS/Win/Linux)
    ├── run.sh          # Quick launch script for desktop client
    ├── requirements.txt# Client dependencies (bleak, websockets, Pillow, pyobjc/pystray)
    ├── main.py         # Client launcher & platform selector
    ├── icon/           # Squircle app icon assets (icon.icns, icon.ico, icon.png)
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

All requests to `/api/*` require authentication via the `X-API-Key` HTTP header.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/print/photo` | **Photo Studio Print:** High-fidelity 1-bit thermal halftoning for photos and artwork with quality presets (`preset`, `dither_algo`, `sharpness`, `contrast`, `brightness`, `strength`). |
| `POST` | `/api/print/raw` | **Upload & Print:** PDF or Image invoice document with auto-scaling, auto-cropping, and strength options. |
| `POST` | `/api/print/text` | **Direct Text Print:** Formatted receipt text supporting all languages and emojis with customizable font size and strength. |
| `POST` | `/api/print/qr` | **Direct QR Code Print:** High-contrast thermal QR code with optional multilingual header and footer text (supports `content` and `text`). |
| `GET` / `POST` | `/api/qr/generate` | **Direct QR Generator:** Directly streams a 384px PNG QR code from query parameters or JSON body (no auth required, ideal for `<img>` tags). |
| `POST` | `/api/print/stop` | **Immediate Stop:** Aborts whatever job is currently streaming to the thermal printer. |
| `DELETE` / `POST` | `/api/print/cancel/{job_id}` | Cancels a pending job or aborts an active printing job by ID. |
| `POST` | `/api/print/confirm/{job_id}` | Confirms a pending job (if submitted with `immediate=false`). |
| `GET` | `/api/print/preview/{job_id}` | Returns a 384px monochrome PNG preview of the rasterized receipt. |
| `GET` | `/api/status` | Probes printer BLE connectivity and returns active transmission status (`is_printing`). |
| `GET` | `/api/queue` | Returns paginated recent job history. |
| `WebSocket` | `/ws/client` | **Cloud Relay Bridge:** Real-time bidirectional WebSocket stream for store client machines (authenticates via `?api_key=...&client_name=...`). |

---

## Integration Code Examples

### 1. High-Quality Photo & Artwork Studio Print (Laravel / PHP)
Send portraits or artwork with Floyd-Steinberg, Atkinson, or Bayer halftoning and unsharp-mask spatial edge sharpening:
```php
<?php
use Illuminate\Support\Facades\Http;

$apiKey  = 'sk_live_your_api_key_here';
$baseUrl = 'https://pos.yourdomain.com'; // or http://localhost:8100

$response = Http::withHeaders([
    'X-API-Key' => $apiKey,
])->attach(
    'file', file_get_contents($photoPath), 'portrait.jpg'
)->post("{$baseUrl}/api/print/photo", [
    'immediate'   => 'true',        // Prints immediately in 1-step!
    'preset'      => 'portrait',    // 'portrait', 'sharp', 'balanced', 'high_contrast', 'halftone'
    'dither_algo' => 'floyd',       // 'floyd' (Floyd-Steinberg), 'atkinson', 'bayer'
    'sharpness'   => 1.2,           // Unsharp-mask spatial edge sharpening (0.0 to 3.0)
    'contrast'    => 1.15,          // Optional contrast boost
    'brightness'  => 1.08,          // Optional shadow lift
    'strength'    => 7,             // 1-7 thermal darkness
    'keepjob'     => 'false',       // Temporary (purged from SQLite after 5m)
]);

$jobId = $response->json('job_id');
```

### 2. Direct 1-Step QR Code Print (cURL & Laravel)
Print payment QR codes, Wi-Fi credentials, or invoice links with sharp alignment and optional multilingual headers/footers:

**cURL:**
```bash
curl -X POST https://pos.yourdomain.com/api/print/qr \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "https://pos.sayem.com/pay/inv_99812",
    "header": "SCAN TO PAY ৳১৫০.০০",
    "footer": "Table #5 • TinyPOS Bridge",
    "qr_size": 260,
    "strength": 7,
    "immediate": true,
    "keepjob": false
  }'
```

**Laravel / PHP:**
```php
$qrRes = Http::withHeaders(['X-API-Key' => $apiKey])
    ->post("{$baseUrl}/api/print/qr", [
        'text'      => 'https://pos.sayem.com/pay/inv_1042',
        'header'    => 'SCAN TO PAY ৳৪৫০.০০',
        'footer'    => 'TinyPOS Thermal Bridge',
        'qr_size'   => 260,
        'strength'  => 7,
        'immediate' => true,
    ]);
```

### 3. Direct QR Code Image Generation & Streaming (HTML `<img>` & cURL)
Streams a 384px monochrome PNG on-the-fly without requiring authentication. Perfect for embedding directly in web receipts or HTML reports:

**HTML `<img>` tag:**
```html
<img src="https://pos.yourdomain.com/api/qr/generate?text=https://pos.sayem.com/order/99&header=TABLE+12&footer=THANK+YOU&size=260" alt="Thermal QR Code" />
```

**cURL save to file:**
```bash
curl -o qr.png "https://pos.yourdomain.com/api/qr/generate?text=https://pos.sayem.com&header=ORDER+99&size=260"
```

### 4. Direct 1-Step Invoice PDF & Document Print (Laravel / PHP)
Send invoice PDFs or documents directly to your printer with automatic margin trimming:
```php
<?php
use Illuminate\Support\Facades\Http;

$response = Http::withHeaders([
    'X-API-Key' => $apiKey,
])->attach(
    'file', file_get_contents($pdfPath), 'invoice.pdf'
)->post("{$baseUrl}/api/print/raw", [
    'immediate' => 'true',
    'scale'     => 1.25,   // 1.25x zoom for 80mm receipts
    'autocrop'  => 'true', // Trims empty white margins
    'strength'  => 7,
]);
```

### 5. Multilingual Text Receipt Print (cURL)
Supports Bangla, Arabic, Hindi, CJK, English, and Emojis seamlessly:
```bash
curl -X POST https://pos.yourdomain.com/api/print/text \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "================================\n       রেস্তোরাঁ এক্সপ্রেস 🍕\n================================\nআইটেম ১             ৳১৫০.০০\nItem 2               $5.00\n--------------------------------\nমোট বিল / TOTAL     ৳২০০.০০\nধন্যবাদ! আবার আসবেন ❤️\n================================",
    "font_size": 22,
    "strength": 7,
    "immediate": true,
    "keepjob": false
  }'
```

### 6. Immediate Stop / Abort Job (cURL)
To abort whatever job is currently transmitting to the printer:
```bash
curl -X POST https://pos.yourdomain.com/api/print/stop \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Key Parameters Reference

### QR Code Parameters (`/api/print/qr` & `/api/qr/generate`)
- `text` / `content` *(string, required)*: The URL, string, or invoice link encoded into the QR matrix.
- `header` *(string, optional)*: Multilingual text printed centered above the QR code.
- `footer` *(string, optional)*: Multilingual text printed centered below the QR code.
- `qr_size` / `size` *(integer, default: `260`)*: QR square dimension in dots (64 to 384).
- `strength` *(integer 1–7, default: `7`)*: Thermal head burning intensity.

### Photo Studio Parameters (`/api/print/photo`)
- `preset` *(string, default: `portrait`)*: Quality preset: `portrait` (smooth face tones), `sharp` (detailed hair/eyes/jewelry), `balanced` (landscapes), `high_contrast` (logos & ink art), `halftone` (retro 8x8 newspaper matrix).
- `dither_algo` *(string, optional)*: Dithering algorithm override: `floyd` (Floyd-Steinberg error diffusion), `atkinson` (Apple Macintosh classic crisp highlights), `bayer` (8x8 ordered halftone).
- `sharpness` *(float, default: `1.2`)*: Unsharp-mask spatial edge sharpening filter (0.0 to 3.0) applied before halftoning.
- `contrast` *(float, optional)*: Dynamic range contrast multiplier (e.g. `1.15`).
- `brightness` *(float, optional)*: Shadow tone lift multiplier (e.g. `1.08`).

### General Execution Parameters
- `immediate` *(boolean, default: `true`)*: When `true`, the job prints immediately in the background without needing a secondary `/confirm` call.
- `scale` *(float, default: `1.0`)*: Zoom/Scale multiplier. Set to `1.25` for 80mm receipts or `1.5` for A4 to expand receipt text cleanly across the 57mm (384-dot) paper width.
- `autocrop` *(boolean, default: `true`)*: Automatically strips empty white borders and margins so receipt content expands to fill the full printable area.
- `strength` *(integer 1–7, default: `7`)*: Thermal head burning energy. Level `7` ensures high contrast and dark characters even on weak, aging, or thin thermal paper.
- `font_size` *(integer, default: `22`)*: Size in points for text printing (recommended: 20–26pt for receipts).
- `keepjob` / `keep_job` *(boolean, default: `false`)*: When `false`, job records and stored preview bitmaps are auto-purged from SQLite after 5 minutes, keeping disk footprint minimal. Set to `true` to preserve records permanently in history.

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
│ e.g. pos.sayem.top      │
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

The desktop client is a native Menu Bar / System Tray application designed to run quietly in the background on store machines.

### Key Capabilities
- **Native Look & Feel**: Uses native Cocoa AppKit on macOS (`NSStatusBar`, `NSMenu`, dynamic colored circle status badges) and `pystray` on Windows/Linux.
- **1-Click Quick Setup**: Copy the WebSocket Connection URL from your TinyPOS server's **Settings** page and click the **📋 Paste** button (or press `Cmd+V` / `Ctrl+V`) to automatically populate Server URL, API Key, and Terminal Name.
- **Dynamic Status Icons**:
  - 🟢 **Green**: Connected to Cloud Relay & Bluetooth Printer Ready.
  - 🟡 **Yellow**: Connected to Cloud Relay, but Printer is Offline or Out of Bluetooth Range.
  - 🔴 **Red**: Disconnected from Cloud Relay / Reconnecting.
  - ⚪ **Gray**: Unconfigured.
- **BLE Resiliency**: Built-in 4-scan debouncing, 25-second post-print cooldown grace period, and device memory to prevent false offline drops on macOS CoreBluetooth duplicate filtering.

### Running in Development
```bash
./client-app/run.sh
```
*or directly:*
```bash
./.venv/bin/python client-app/main.py
```

### Packaging Standalone Binaries (`build.py`)

You can compile TinyPOS into a single standalone application without needing Python installed on the target machine:

```bash
cd client-app
python3 build.py
```

| Platform | Output Artifact | Description |
|---|---|---|
| **macOS** | `dist/TinyPOS.app` | Native macOS Application Bundle with Retina `icon.icns`, background menu bar mode, and Cocoa Edit shortcuts. |
| **Windows** | `dist/TinyPOS.exe` | Single-file standalone executable with embedded `icon.ico` and no console window. |
| **Linux** | `dist/TinyPOS` | Single-file standalone binary with `icon.png` and system tray integration. |

*Note: All intermediate build caches (`build/`, `.spec` files, `__pycache__`) are automatically removed immediately upon build completion.*

---

## Running Verification Tests
TinyPOS includes an automated end-to-end test suite covering SQLite CRUD, Authentication, 1-Step Printing, Temporary Job Cleanup, Stop/Cancel APIs, and Universal Multi-Language Text Rendering:

```bash
.venv/bin/python test_app.py
```

---

## License
MIT License. Free for commercial and personal POS deployments.
