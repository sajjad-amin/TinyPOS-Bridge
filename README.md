# TinyPOS &bull; Thermal POS Bridge Application

**TinyPOS** is a cross-platform, lightweight FastAPI bridge that connects web applications (Laravel, ERPNext, custom POS software) to local Bluetooth Low Energy (BLE) thermal receipt printers running the **Bainiu / Tiny Print** protocol (such as X6, X5, C9, iPrint, etc.).

It runs seamlessly on macOS, Linux, Raspberry Pi, and Windows, exposing both a modern Web Dashboard and a REST API with 1-step direct printing, mid-stream print cancellation, universal multi-language support, and auto-scaling for 80mm/A4 receipts.

---

## Key Features

- **100% Universal World Language & Emoji Support:** Print receipts in any living language on Earth — Bengali, Arabic, Urdu, English, Chinese, Hindi, Russian, Japanese, Telugu, Tamil, Korean, Thai, Gujarati, Kannada, Malayalam, Odia, Burmese, Punjabi, Ethiopic/Amharic, Lao, Khmer, Sinhala, Greek, Hebrew, Armenian, Georgian, and all Emojis — seamlessly mixed on the same line without missing glyph boxes.
- **Direct 1-Step Printing:** Print formatted text, receipts, or PDF/image files immediately via REST API or the Web UI.
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
| `POST` | `/api/print/raw` | **Upload & Print:** PDF or Image with auto-scaling, auto-cropping, and strength options. |
| `POST` | `/api/print/text` | **Direct Text Print:** Formatted receipt text supporting all languages and emojis with customizable font size and strength. |
| `POST` | `/api/print/stop` | **Immediate Stop:** Aborts whatever job is currently streaming to the thermal printer. |
| `DELETE` / `POST` | `/api/print/cancel/{job_id}` | Cancels a pending job or aborts an active printing job by ID. |
| `POST` | `/api/print/confirm/{job_id}` | Confirms a pending job (if submitted with `immediate=false`). |
| `GET` | `/api/print/preview/{job_id}` | Returns a 384px monochrome PNG preview of the rasterized receipt. |
| `GET` | `/api/status` | Probes printer BLE connectivity and returns active transmission status (`is_printing`). |
| `GET` | `/api/queue` | Returns paginated recent job history. |

---

## Integration Code Examples

### 1. Direct 1-Step File Print (Laravel / PHP)
Send invoice PDFs or images directly from Laravel to your printer:
```php
<?php
use Illuminate\Support\Facades\Http;

$apiKey  = 'sk_live_your_api_key_here';
$baseUrl = 'https://pos.yourdomain.com'; // or http://localhost:8100

$response = Http::withHeaders([
    'X-API-Key' => $apiKey,
])->attach(
    'file', file_get_contents($pdfPath), 'invoice.pdf'
)->post("{$baseUrl}/api/print/raw", [
    'immediate' => 'true',  // Prints immediately in 1-step!
    'scale'     => 1.25,    // 1.25x zoom for 80mm receipts (1.5x for A4)
    'autocrop'  => 'true',  // Trims empty white margins
    'strength'  => 7,       // 1-7: max thermal burn darkness
    'keepjob'   => 'false', // Temporary (purged from SQLite after 5m)
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

### 3. Immediate Stop / Abort Job (cURL)
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
