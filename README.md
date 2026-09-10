# TinyPOS &bull; Thermal POS Bridge Application

**TinyPOS** is a cross-platform, lightweight FastAPI bridge that connects web applications (Laravel, ERPNext, custom POS software) to local Bluetooth Low Energy (BLE) thermal receipt printers running the **Bainiu / Tiny Print** protocol (such as X6, X5, C9, iPrint, etc.).

It runs seamlessly on macOS, Linux, Raspberry Pi, and Windows, exposing both a modern Web Dashboard and a REST API with 1-step direct printing, mid-stream print cancellation, and auto-scaling for 80mm/A4 receipts.

---

## Key Features

- **Direct 1-Step Printing:** Print formatted text, receipts, or PDF/image files immediately via REST API or the Web UI.
- **Live Job Cancellation:** Stop and abort active print jobs mid-stream from the dashboard or API to prevent paper waste.
- **Receipt Auto-Scaling & Margin Cropping:** Automatically crop white borders and scale 80mm/A4 receipts to fit 57mm rolls cleanly.
- **Adjustable Print Darkness (1–7):** Fine-tune thermal burn strength for faint or aged paper rolls.
- **Cross-Platform:** Runs natively on macOS, Linux, Raspberry Pi, and Windows without OS-specific dependencies.
- **Storage & Memory Protection:** Automatically purges temporary print jobs after 5 minutes to prevent database bloat.
- **Modern Web Dashboard:** Manage API keys, monitor recent jobs, test printer hardware, and view interactive API docs.

---

## Directory Structure
```
TinyPOS/
├── .env                # Local configuration (ADMIN_USERNAME, ADMIN_PASSWORD, PORT, HOST)
├── .env.example        # Environment configuration template
├── .gitignore          # Rules for venv, caches, SQLite DBs, logs, and secrets
├── requirements.txt    # Python dependencies
├── main.py             # FastAPI entrypoint & background cleaner lifecycle
├── printer_ble.py      # Cross-platform BLE driver, Bainiu protocol, rasterizer
├── test_app.py         # Test suite (DB, Auth, UI, Direct Printing, Stop Controls)
├── tinypos.db          # SQLite database (auto-created on launch)
├── ecosystem.config.js # PM2 process manager configuration
├── server/             # Modular server core
│   ├── config.py       # Configuration & environment variables
│   ├── db.py           # SQLite operations (jobs and api_keys tables)
│   ├── auth.py         # Session auth & API Key validation
│   ├── services/
│   │   └── print_service.py # Background print execution & cleanup scheduler
│   └── routes/
│       ├── web.py          # Dashboard routes (Login, Console, Keys, Docs)
│       ├── internal_api.py # AJAX endpoints for Web Console, Stop, & Queue
│       └── public_api.py   # REST API for external integrations (Laravel, POS)
└── UI/                 # Web Dashboard
    ├── layouts/
    │   ├── app.html    # Master dashboard layout (sidebar, sticky footer, responsive)
    │   └── guest.html  # Clean responsive layout for login
    ├── auth/
    │   └── login.html  # Login view with session auth
    ├── test/
    │   └── index.html  # Test Console: BLE scan, Text print, File print, Stop buttons, Queue
    ├── api_keys/
    │   ├── index.html  # API Keys CRUD: Create modal, copy/reveal, delete modal
    │   └── history.html# Per-API-key print history with pagination & bulk clear
    └── documentation/
        └── index.html  # Interactive API guide with live dynamic Base URL code tabs
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
| `POST` | `/api/print/text` | **Direct Text Print:** Formatted plain text receipt with customizable font size and strength. |
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

### 2. Direct 1-Step Text Print (cURL)
```bash
curl -X POST https://pos.yourdomain.com/api/print/text \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "================================\n       ACME STORE #101\n================================\nItem 1               $15.00\nItem 2                $5.00\n--------------------------------\nTOTAL PAID           $20.00\n================================",
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
- `keepjob` / `keep_job` *(boolean, default: `false`)*: When `false`, job records and stored preview bitmaps are auto-purged from SQLite after 5 minutes, keeping disk footprint minimal. Set to `true` to preserve records permanently in history.

---

## Running Verification Tests
TinyPOS includes an automated end-to-end test suite covering SQLite CRUD, Authentication, 1-Step Printing, Temporary Job Cleanup, and Stop/Cancel APIs:

```bash
.venv/bin/python test_app.py
```
Expected output:
```
--> Testing SQLite API Keys CRUD...
 [OK] SQLite key insertion & validation verified
--> Testing Authentication & UI Routes...
 [OK] / redirected to /login
 [OK] /test (Default Page) rendered cleanly
--> Testing Stop Printing API & UI Controls...
 [OK] Test UI includes Stop buttons for both text and file
 [OK] /api/print/stop endpoint handled idle status cleanly
 [OK] Public /api/print/cancel/{job_id} successfully stopped active printing job

🎉 ALL TESTS (KEEPJOB LIFECYCLE, STOP API, UI CONTROLS & SQLITE) PASSED SUCCESSFULLY!
```

---

## License
MIT License. Free for commercial and personal POS deployments.
