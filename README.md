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
├── .gitignore          # Rules for venv, caches, SQLite DBs, logs, and secrets
├── requirements.txt    # Python dependencies
├── main.py             # FastAPI entrypoint & background cleaner lifecycle
├── printer_ble.py      # BLE printer connection & hardware transport driver
├── engine/             # Printing engine (text layout, fonts, protocol, bitmap rendering)
├── fonts/              # Cross-platform bundled fonts for universal script support
├── test_app.py         # Comprehensive automated test suite
├── tinypos.db          # SQLite database (auto-created on launch)
├── ecosystem.config.js # PM2 process manager configuration
├── server/             # Modular server core (auth, database, print service, routes)
└── UI/                 # Web Dashboard (console, API keys, login, docs)
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
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/print/raw` | **Upload & Print:** PDF or Image with auto-scaling, auto-cropping, and strength options. Supports `mode=photo` (or `dither=true`) for realistic Floyd-Steinberg photo dithering. |
| `POST` | `/api/print/text` | **Direct Text Print:** Formatted receipt text supporting all languages and emojis with customizable font size and strength. |
| `POST` | `/api/print/qr` | **Direct QR Code Print:** High-contrast thermal QR code with optional multilingual header and footer text (supports `content` and `text`). |
| `GET` / `POST` | `/api/qr/generate` | **Direct QR Generator:** Directly streams a 384px PNG QR code from query parameters or JSON body (no auth required, ideal for `<img>` tags). |
| `POST` | `/api/print/stop` | **Immediate Stop:** Aborts whatever job is currently streaming to the thermal printer. |
| `DELETE` / `POST` | `/api/print/cancel/{job_id}` | Cancels a pending job or aborts an active printing job by ID. |
| `POST` | `/api/print/confirm/{job_id}` | Confirms a pending job (if submitted with `immediate=false`). |
| `GET` | `/api/print/preview/{job_id}` | Returns a 384px monochrome PNG preview of the rasterized receipt. |
| `GET` | `/api/status` | Probes printer BLE connectivity and returns active transmission status (`is_printing`). |
| `GET` | `/api/queue` | Returns paginated recent job history. |

---

## Integration Code Examples

### 1. Direct 1-Step File & Photo Print (Laravel / PHP)
Send invoice PDFs, receipts, or photos directly from Laravel to your printer. Use `'mode' => 'photo'` for realistic photographic shading:
```php
<?php
use Illuminate\Support\Facades\Http;

$apiKey  = 'sk_live_your_api_key_here';
$baseUrl = 'https://pos.yourdomain.com'; // or http://localhost:8100

$response = Http::withHeaders([
    'X-API-Key' => $apiKey,
])->attach(
    'file', file_get_contents($imagePath), 'portrait.jpg'
)->post("{$baseUrl}/api/print/raw", [
    'immediate' => 'true',   // Prints immediately in 1-step!
    'mode'      => 'photo',  // 'photo' for Floyd-Steinberg dithering; 'text' for receipts
    'scale'     => 1.0,      // 1.0 = fit 384px width; 1.25 = +25% zoom
    'autocrop'  => 'true',   // Trims empty white borders
    'strength'  => 7,        // 1-7 thermal darkness
    'keepjob'   => 'false',  // Temporary (purged from SQLite after 5m)
]);

$jobId = $response->json('job_id');
```

### 2. Direct 1-Step Text Print with Multi-Language Support (cURL)
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

### 3. Direct 1-Step QR Code Print (cURL)
Print payment QR codes, Wi-Fi logins, or URL tickets with sharp pixel-perfect alignment:
```bash
curl -X POST https://pos.yourdomain.com/api/print/qr \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "https://pos.sayem.com/pay/inv_99812",
    "header": "SCAN TO PAY ৳১৫০.০০",
    "footer": "TinyPOS Thermal Bridge",
    "qr_size": 260,
    "strength": 7,
    "immediate": true,
    "keepjob": false
  }'
```

### 4. Direct QR Code Image Generation (HTML / URL)
Directly embed or stream a 384px thermal QR code PNG into any webpage, invoice, or application:
```html
<img src="https://pos.yourdomain.com/api/qr/generate?text=https://pos.sayem.com&header=TABLE+12&footer=THANK+YOU&size=260" alt="QR Code" />
```

### 4. Immediate Stop / Abort Job (cURL)
To abort whatever job is currently transmitting to the printer:
```bash
curl -X POST https://pos.yourdomain.com/api/print/stop \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Key Parameters Explained

- `immediate` *(boolean, default: `true`)*: When `true`, the job prints immediately in the background without needing a secondary `/confirm` call.
- `scale` *(float, default: `1.0`)*: Zoom/Scale multiplier. Set to `1.25` for 80mm receipts or `1.5` for A4 to expand receipt text cleanly across the 57mm (384-dot) paper width.
- `autocrop` *(boolean, default: `true`)*: Automatically strips empty white borders and margins so receipt content expands to fill the full printable area.
- `strength` *(integer 1–7, default: `7`)*: Thermal head burning energy. Level `7` ensures high contrast and dark characters even on weak, aging, or thin thermal paper.
- `font_size` *(integer, default: `22`)*: Size in points for text printing (recommended: 20–26pt for receipts).
- `keepjob` / `keep_job` *(boolean, default: `false`)*: When `false`, job records and stored preview bitmaps are auto-purged from SQLite after 5 minutes, keeping disk footprint minimal. Set to `true` to preserve records permanently in history.

---

## Running Verification Tests
TinyPOS includes an automated end-to-end test suite covering SQLite CRUD, Authentication, 1-Step Printing, Temporary Job Cleanup, Stop/Cancel APIs, and Universal Multi-Language Text Rendering:

```bash
.venv/bin/python test_app.py
```

---

## License
MIT License. Free for commercial and personal POS deployments.
