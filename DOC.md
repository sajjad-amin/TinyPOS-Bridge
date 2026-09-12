# TinyPOS Developer Integration Guide & API Specification (v1.0.0)

> Complete technical documentation for integrating point-of-sale (POS) systems, e-commerce platforms, ERPs, and custom applications with **TinyPOS Thermal Printer Bridge**.

---

## Table of Contents
1. [Overview & System Architecture](#1-overview--system-architecture)
2. [Hardware & Thermal Specifications](#2-hardware--thermal-specifications)
3. [Authentication & Multi-Tenant Security](#3-authentication--multi-tenant-security)
4. [API Endpoints Quick Reference](#4-api-endpoints-quick-reference)
5. [Invoices & Raw Documents API (`/api/print/raw`)](#5-invoices--raw-documents-api-apiprintraw)
6. [Photo Studio API (`/api/print/photo`)](#6-photo-studio-api-apiprintphoto)
7. [Multilingual Text API (`/api/print/text`)](#7-multilingual-text-api-apiprinttext)
8. [Thermal QR Code API (`/api/print/qr`)](#8-thermal-qr-code-api-apiprintqr)
9. [Direct PNG QR Generator (`/api/qr/generate`)](#9-direct-png-qr-generator-apiqrgenerate)
10. [Paper Feed API (`/api/print/feed`)](#10-paper-feed-api-apiprintfeed)
11. [Emergency Stop API (`/api/print/stop`)](#11-emergency-stop-api-apiprintstop)
12. [Job Cancellation API (`/api/print/cancel/{job_id}`)](#12-job-cancellation-api-apiprintcanceljob_id)
13. [Job Confirmation API (`/api/print/confirm/{job_id}`)](#13-job-confirmation-api-apiprintconfirmjob_id)
14. [Raster Preview API (`/api/print/preview/{job_id}`)](#14-raster-preview-api-apiprintpreviewjob_id)
15. [Print Queue API (`/api/queue`)](#15-print-queue-api-apiqueue)
16. [Hardware & Relay Status API (`/api/status`)](#16-hardware--relay-status-api-apistatus)
17. [Cloud Relay WebSocket Protocol (`/ws/client`)](#17-cloud-relay-websocket-protocol-wsclient)
18. [Best Practices & Production Deployment](#18-best-practices--production-deployment)

---

## 1. Overview & System Architecture

TinyPOS operates in two primary operational topologies:

```
[POS System / Web App]
        │
        ▼ (HTTPS REST API with X-API-Key)
┌───────────────────────────────────────────────────────────┐
│              TinyPOS Server (FastAPI + SQLite)            │
│  - Bitmap Rasterization & Scaling                         │
│  - Floyd-Steinberg / Atkinson / Bayer Dithering Engine    │
│  - Multilingual Complex Text Shaping (HarfBuzz + Pillow)  │
│  - Multi-Tenant Terminal Group Routing                    │
└─────────────┬───────────────────────────────┬─────────────┘
              │ Mode: Bluetooth               │ Mode: Cloud Relay
              ▼                               ▼
    ┌──────────────────┐          ┌───────────────────────┐
    │ Local BLE Driver │          │ WSS /ws/client Relay  │
    └─────────┬────────┘          └───────────┬───────────┘
              │ Direct Bluetooth              │ WebSocket over Internet
              ▼                               ▼
    ┌──────────────────┐          ┌───────────────────────┐
    │  Thermal Printer │          │ Store Client Terminal │
    │  (Bainiu X6 etc) │          │ (Windows / macOS/Linux│
    └──────────────────┘          └───────────┬───────────┘
                                              │ Local Bluetooth
                                              ▼
                                  ┌───────────────────────┐
                                  │  Thermal Printer(s)   │
                                  └───────────────────────┘
```

1. **Direct Bluetooth Mode (Local/Single-Machine):**
   The TinyPOS server communicates directly with the thermal printer via Bluetooth Low Energy (BLE).
2. **Cloud Relay Mode (Multi-Branch / Multi-Terminal):**
   The TinyPOS server runs on a VPS or cloud host (`https://your-pos-server.com`). Physical store machines run the lightweight **TinyPOS Bridge Client App**, which connects over secure WebSockets (`wss://your-pos-server.com/ws/client`) and forwards print jobs to the local BLE printer. Multiple client terminals can be organized into **Tenant Groups** (e.g., `Kitchen`, `Cashier-1`, `Bar`) with automatic signal strength (RSSI) steering.

---

## 2. Hardware & Thermal Specifications

| Specification | Value | Description |
| :--- | :--- | :--- |
| **Print Head Width** | **384 dots (pixels)** | 48 bytes per horizontal scanline (1 dot = 1 bit). |
| **Paper Roll Width** | **57–58 mm** | Standard receipt paper roll (printable width ~48 mm). |
| **Resolution** | **203 DPI (8 dots/mm)** | Standard thermal receipt resolution. |
| **Color Depth** | **1-bit Monochrome** | Black (printed dot = `1`), White (unprinted dot = `0`). |
| **Byte Encoding** | **LSB First** | Bit 7 represents the leftmost pixel; Bit 0 represents the rightmost pixel in each byte. |
| **Line Feed Command** | `ESC J <n>` (`0x1B 0x4A <n>`) | Feeds paper by `n` vertical dots. Standard feed sequence: `\x1b\x4a\x40` (64 dots). |
| **Print Speed / Darkness** | **Levels 1 to 7** | Configures thermal element burn pulse duration. Default: `7` (maximum contrast). |

---

## 3. Authentication & Multi-Tenant Security

TinyPOS implements robust API authentication across 100% of its API endpoints to prevent unauthorized printing, denial-of-service, and resource exhaustion:

### 1. HTTP Header Authentication (Standard)
All transactional, printing, and job control endpoints (`/api/print/*`, `/api/printer/*`, `/api/queue`, `/api/status`) require your valid API key passed via the `X-API-Key` HTTP header:

```http
X-API-Key: sk_live_your_api_key_here
Accept: application/json
```

### 2. URL Query Parameter Authentication (Media & `<img>` Tags)
For endpoints that serve image streams directly to web browsers, mobile webviews, or HTML `<img>` tags (`/api/qr/generate` and `/api/print/preview/{job_id}`), you may authenticate by passing `?api_key=` (or `?key=`) as a query parameter:

```html
<img src="https://your-pos-server.com/api/qr/generate?api_key=sk_live_your_key&text=https://sajjadamin.com/pay/101" alt="Thermal QR Code" />
```

### 3. Active Admin Session Cookie
When logged into the TinyPOS admin dashboard, preview and media endpoints automatically accept your active session cookie (`tinypos_session=admin_authenticated`), enabling seamless print history viewing and queue previews without exposing API keys in client-side templates or JavaScript.

> [!NOTE]
> All unauthenticated requests to any `/api/*` endpoint are rejected with `403 Forbidden`.

### Multi-Tenant Group Binding (Cloud Relay Mode)
When TinyPOS is configured in **Cloud Relay** mode:
- Each client terminal belongs to a named group (e.g. `Kitchen`, `Counter-1`).
- Each external API key is bound to an authorized group in the TinyPOS dashboard.
- Print jobs initiated with that API key are routed specifically to the terminals in that group. If no terminals in the group are connected, the API responds with a descriptive `500 Internal Server Error`.

---

## 4. API Endpoints Quick Reference

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/print/raw` | Upload & print PDF invoice or image file | `X-API-Key` |
| `POST` | `/api/print/photo` | High-fidelity photo halftoning (5 presets, 3 dither algorithms) | `X-API-Key` |
| `POST` | `/api/print/text` | Multilingual text receipt (universal living languages + emojis) | `X-API-Key` |
| `POST` | `/api/print/qr` | Thermal QR code with header & footer text | `X-API-Key` |
| `GET` / `POST` | `/api/qr/generate` | Stream 384px PNG QR code directly (for `<img>` tags & downloads) | `X-API-Key` or `?api_key=` |
| `POST` | `/api/print/feed` | Advance/feed thermal receipt paper roll (alias: `/api/printer/feed`) | `X-API-Key` |
| `POST` | `/api/print/stop` | Emergency immediate transmission abort | `X-API-Key` |
| `DELETE` / `POST`| `/api/print/cancel/{id}` | Cancel pending job or stop active printing job by ID | `X-API-Key` |
| `POST` | `/api/print/confirm/{id}` | Confirm and execute a pending queued job | `X-API-Key` |
| `GET` | `/api/print/preview/{id}` | Stream 384px 1-bit monochrome PNG preview | `X-API-Key`, `?api_key=`, or Admin Session |
| `GET` | `/api/queue` | List paginated jobs and status | `X-API-Key` |
| `GET` | `/api/status` | Probe printer online/offline & active printing state | `X-API-Key` |

---

## 5. Invoices & Raw Documents API (`/api/print/raw`)

Upload and print arbitrary PDF documents, invoices, vouchers, or images (JPG, PNG, WebP). PDFs are automatically rendered at high DPI, zoomed to fit 384 dots, cropped of empty margins, and rasterized to 1-bit monochrome.

### Endpoint
`POST /api/print/raw` (Multipart Form-Data)

### Parameters
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `file` | File | **Required** | The PDF or Image file (binary). |
| `scale` | float | `1.0` | Scaling multiplier (`1.25` recommended for 80mm receipts, `1.5` for A4 invoices). |
| `autocrop` | bool | `true` | Automatically detects and removes surrounding white margins. |
| `mode` | string | `"text"` | Rendering mode: `"text"` (high-contrast threshold) or `"photo"` (halftoning). |
| `dither` | bool | `false` | Enable error-diffusion dithering (equivalent to `mode=photo`). |
| `strength` | int | `7` | Thermal darkness (1 to 7). |
| `immediate` | bool | `true` | If `true`, directly prints in background. If `false`, enters `pending` state. |
| `keep_job` / `keepjob` | bool | `false` | If `false`, automatically deleted after 5m to prevent database bloat. |

### Code Examples

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/raw \
  -H "X-API-Key: sk_live_your_api_key_here" \
  -F "file=@invoice.pdf" \
  -F "scale=1.25" \
  -F "autocrop=true" \
  -F "strength=7" \
  -F "immediate=true"
```

#### JavaScript (Node.js / Browser)
```javascript
const formData = new FormData();
formData.append('file', invoiceFile);
formData.append('scale', '1.25');
formData.append('autocrop', 'true');
formData.append('strength', '7');
formData.append('immediate', 'true');

const res = await fetch('https://your-pos-server.com/api/print/raw', {
  method: 'POST',
  headers: { 'X-API-Key': 'sk_live_your_api_key_here' },
  body: formData
});
const data = await res.json();
console.log('Print Job Dispatched:', data.job_id);
```

#### Python (`requests`)
```python
import requests

with open("invoice.pdf", "rb") as f:
    res = requests.post(
        "https://your-pos-server.com/api/print/raw",
        headers={"X-API-Key": "sk_live_your_api_key_here"},
        files={"file": f},
        data={"scale": 1.25, "autocrop": "true", "strength": 7, "immediate": "true"}
    )
print("Job ID:", res.json()["job_id"])
```

#### PHP (Laravel `Http`)
```php
use Illuminate\Support\Facades\Http;

$response = Http::withHeaders(['X-API-Key' => 'sk_live_your_api_key_here'])
    ->attach('file', file_get_contents('/path/to/invoice.pdf'), 'invoice.pdf')
    ->post('https://your-pos-server.com/api/print/raw', [
        'scale'     => 1.25,
        'autocrop'  => 'true',
        'strength'  => 7,
        'immediate' => 'true',
    ]);
echo "Job ID: " . $response->json('job_id');
```

---

## 6. Photo Studio API (`/api/print/photo`)

Provides photographic halftoning algorithms specifically tuned for 203 DPI thermal paper. Includes tone curve adjustments, unsharp masking edge enhancement, and error-diffusion dithering.

### Endpoint
`POST /api/print/photo` (Multipart Form-Data)

### Quality Presets
| Preset | Characteristics | Best For |
| :--- | :--- | :--- |
| `portrait` *(Default)* | Lifts shadows (+8% brightness), soft Floyd-Steinberg error diffusion | Human faces, portraits, ID photos |
| `sharp` | Boosts unsharp-masking to 200% for fine lines and textures | Intricate jewelry, fine hair, architecture |
| `balanced` | Neutral tonal curve preserving both dark shadows and bright highlights | Landscapes, general photography |
| `high_contrast` | Aggressive thresholding with deep black punch | Line art, logos, black & white sketches |
| `halftone` | 8x8 Bayer ordered dot-matrix pattern | Vintage newspaper aesthetic |

### Parameters
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `file` | File | **Required** | Image file (JPG, PNG, WebP). |
| `preset` | string | `"portrait"` | Quality preset (`portrait`, `sharp`, `balanced`, `high_contrast`, `halftone`). |
| `dither_algo` | string | Preset Default | Algorithm: `floyd` (Floyd-Steinberg), `atkinson`, `bayer`. |
| `sharpness` | float | `1.2` | Unsharp mask enhancement (0.0 to 3.0). |
| `contrast` | float | `1.15` | Contrast multiplier. |
| `brightness` | float | `1.08` | Brightness multiplier. |
| `strength` | int | `7` | Thermal darkness (1 to 7). |
| `immediate` | bool | `true` | Direct print execution. |

### Code Examples

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/photo \
  -H "X-API-Key: sk_live_your_api_key_here" \
  -F "file=@portrait.jpg" \
  -F "preset=portrait" \
  -F "dither_algo=floyd" \
  -F "sharpness=1.2" \
  -F "immediate=true"
```

#### Python
```python
import requests

with open("portrait.jpg", "rb") as f:
    res = requests.post(
        "https://your-pos-server.com/api/print/photo",
        headers={"X-API-Key": "sk_live_your_api_key_here"},
        files={"file": f},
        data={"preset": "portrait", "dither_algo": "floyd", "sharpness": 1.2, "immediate": "true"}
    )
print("Photo Job ID:", res.json()["job_id"])
```

---

## 7. Multilingual Text API (`/api/print/text`)

TinyPOS includes a universal Unicode shaping and rendering engine capable of mixing **all living world languages and emojis on the same line** without broken ligatures or missing font glyph boxes:
- **Indic Scripts:** Bengali (বাংলা), Hindi (हिन्दी), Tamil, Telugu, Malayalam, Gujarati, etc.
- **RTL Scripts:** Arabic (العربية), Urdu (اردو), Persian, Hebrew.
- **CJK Scripts:** Simplified Chinese (简体中文), Traditional Chinese (繁體中文), Japanese (日本語), Korean (한국어).
- **Latin & Cyrillic:** English, Spanish, French, German, Russian (Русский).
- **Southeast Asian:** Thai (ไทย), Vietnamese.
- **Color & Monochrome Emojis:** 🍕☕❤️🎉✅

### Endpoint
`POST /api/print/text` (JSON Payload)

### Parameters
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `text` | string | **Required** | Receipt text. Use `\n` for line breaks. |
| `font_size` | int | `22` | Font size in points (recommended: 18 to 26). |
| `strength` | int | `7` | Thermal darkness (1 to 7). |
| `immediate` | bool | `true` | Direct print execution. |
| `keep_job` / `keepjob` | bool | `false` | Permanent storage in database. |

### Code Examples

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/text \
  -H "X-API-Key: sk_live_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "================================\n       RESTAURANT EXPRESS 🍕\n================================\nচিকেন বিরিয়ানি (Half)    ৳২০০.০০\nChicken Shawarma         $5.50\nMineral Water (500ml)    ৳২৫.০০\n--------------------------------\nসর্বমোট বিল / TOTAL     ৳২৮০.০০\nধন্যবাদ! আবার আসবেন ❤️\n================================",
    "font_size": 22,
    "strength": 7,
    "immediate": true
  }'
```

#### JavaScript
```javascript
const res = await fetch('https://your-pos-server.com/api/print/text', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'sk_live_your_api_key_here'
  },
  body: JSON.stringify({
    text: "ACME STORE 🍕\nবিল: ৳৪৫০.০০\nThank You! ❤️",
    font_size: 22,
    immediate: true
  })
});
const data = await res.json();
console.log('Text Job ID:', data.job_id);
```

---

## 8. Thermal QR Code API (`/api/print/qr`)

Generates high-contrast thermal-optimized QR codes with optional centered multilingual text headers and footers, dispatched directly to the printer.

### Endpoint
`POST /api/print/qr` (JSON Payload)

### Parameters
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `text` / `content` | string | **Required** | URL, payment string (UPI, bKash, PayPal), or raw data. |
| `header` | string | `null` | Optional centered multilingual text above QR code. |
| `footer` | string | `null` | Optional centered multilingual text below QR code. |
| `qr_size` / `size` | int | `260` | Pixel dimensions of QR code square (64 to 384 dots). |
| `strength` | int | `7` | Thermal darkness (1 to 7). |
| `immediate` | bool | `true` | Direct print execution. |

### Code Examples

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/qr \
  -H "X-API-Key: sk_live_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "https://sajjadamin.com/pay/inv_1042",
    "header": "TABLE #5 • স্ক্যান করে পে করুন",
    "footer": "Scan to Pay Online",
    "qr_size": 260,
    "strength": 7,
    "immediate": true
  }'
```

#### Python
```python
import requests

res = requests.post(
    "https://your-pos-server.com/api/print/qr",
    headers={"X-API-Key": "sk_live_your_api_key_here"},
    json={
        "text": "https://sajjadamin.com/pay/inv_1042",
        "header": "TABLE #5",
        "footer": "Scan to Pay",
        "qr_size": 260,
        "immediate": True,
    }
)
print("QR Job ID:", res.json()["job_id"])
```

---

## 9. Direct PNG QR Generator (`/api/qr/generate`)

A dedicated utility endpoint that streams a 384px-wide thermal-optimized monochrome PNG image on the fly. Ideal for direct embedding into HTML `<img>` tags, PDF invoices, or web dashboards.

> [!IMPORTANT]
> **Authentication Required:** Protected endpoint. Requires an API key via `X-API-Key` HTTP header, `?api_key=` (or `?key=`) URL query parameter, or active admin session cookie. Unauthenticated requests return `403 Forbidden`.

### Endpoints
- `GET /api/qr/generate?api_key=YOUR_KEY&text=...&header=...&footer=...&size=260`
- `POST /api/qr/generate` (JSON with `X-API-Key` header or `?api_key=`)

### HTML Image Tag Embed Example
```html
<img src="https://your-pos-server.com/api/qr/generate?api_key=sk_live_your_key_here&text=https://sajjadamin.com/pay/101&header=TABLE+5&size=260" alt="Thermal QR Code" />
```

### cURL Download
```bash
curl -o thermal_qr.png "https://your-pos-server.com/api/qr/generate?api_key=sk_live_your_key_here&text=https://sajjadamin.com&header=ORDER+99&size=260"
```

---

## 10. Paper Feed API (`/api/print/feed`)

Advances / feeds the thermal receipt roll by standard line feed steps, allowing the cashier or customer to cleanly tear off printed receipts. Works seamlessly across both local Bluetooth and Cloud Relay modes.

### Endpoints
- `POST /api/print/feed`
- `POST /api/printer/feed` *(alias)*

### Headers
```http
X-API-Key: sk_live_your_api_key_here
```

### Response (200 OK)
```json
{
  "success": true,
  "message": "Feed paper command sent to thermal printer."
}
```

### Code Examples

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/feed \
  -H "X-API-Key: sk_live_your_api_key_here"
```

#### JavaScript
```javascript
const res = await fetch('https://your-pos-server.com/api/print/feed', {
  method: 'POST',
  headers: { 'X-API-Key': 'sk_live_your_api_key_here' }
});
console.log('Feed Result:', await res.json());
```

#### Python
```python
import requests

res = requests.post(
    "https://your-pos-server.com/api/print/feed",
    headers={"X-API-Key": "sk_live_your_api_key_here"}
)
print("Feed Result:", res.json())
```

#### PHP
```php
$res = Http::withHeaders(['X-API-Key' => 'sk_live_your_api_key_here'])
    ->post('https://your-pos-server.com/api/print/feed');
```

---

## 11. Emergency Stop API (`/api/print/stop`)

Immediately halts any print transmission actively streaming packets to the printer hardware. This saves thermal paper rolls if a user accidentally sends a 100-page document or wrong invoice.

### Endpoint
`POST /api/print/stop`

### Response (200 OK)
```json
{
  "success": true,
  "message": "Print transmission stopped successfully.",
  "job_id": "3da164e0-833f-4d7d-9f97-67115dbb1061"
}
```

#### cURL
```bash
curl -X POST https://your-pos-server.com/api/print/stop \
  -H "X-API-Key: sk_live_your_api_key_here"
```

---

## 12. Job Cancellation API (`/api/print/cancel/{job_id}`)

Cancels a queued job in `pending` status, or stops an actively transmitting job matching `job_id`.

### Endpoints
- `DELETE /api/print/cancel/{job_id}`
- `POST /api/print/cancel/{job_id}`

### Response (200 OK)
```json
{
  "job_id": "4f9b8c12-3456-789a-bcde-0123456789ab",
  "status": "cancelled",
  "message": "Job cancelled."
}
```

---

## 13. Job Confirmation API (`/api/print/confirm/{job_id}`)

When submitting jobs with `immediate=false`, the server queues the job with `pending` status. Calling this endpoint confirms and initiates hardware transmission.

### Endpoint
`POST /api/print/confirm/{job_id}`

### Response (200 OK)
```json
{
  "job_id": "4f9b8c12-3456-789a-bcde-0123456789ab",
  "status": "printing",
  "message": "Print job confirmed and queued for transmission."
}
```

---

## 14. Raster Preview API (`/api/print/preview/{job_id}`)

Fetches the exact 384px-wide 1-bit monochrome raster image rendered for any job in the database.

> [!IMPORTANT]
> **Authentication Required:** Protected endpoint. Requires an API key via `X-API-Key` header, `?api_key=` URL query parameter, or active admin session cookie (`tinypos_session`). Unauthenticated requests return `403 Forbidden`.

### Endpoint
`GET /api/print/preview/{job_id}`

### HTML Image Tag Embed Example
```html
<img src="https://your-pos-server.com/api/print/preview/550e8400-e29b-41d4-a716-446655440000?api_key=sk_live_your_key_here" alt="Receipt Preview" />
```

### cURL Download
```bash
curl -H "X-API-Key: sk_live_your_key_here" \
  -o preview.png \
  "https://your-pos-server.com/api/print/preview/550e8400-e29b-41d4-a716-446655440000"
```

### Response
Returns binary `image/png` stream.

---

## 15. Print Queue API (`/api/queue`)

Returns a paginated list of print jobs, timestamps, statuses, and options from the SQLite database.

### Endpoint
`GET /api/queue?page=1&per_page=50`

### Parameters
| Query Param | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `page` | int | `1` | Page number. |
| `per_page` | int | `50` | Records per page. |

---

## 16. Hardware & Relay Status API (`/api/status`)

Probes thermal printer connectivity status for the authorized API key's group. In direct Bluetooth mode, it probes BLE hardware; in Cloud Relay mode, it checks active connected client terminals.

### Endpoint
`GET /api/status`

### Response Example (Online)
```json
{
  "status": "online",
  "connected": true,
  "mode": "bluetooth",
  "device_name": "Bainiu X6",
  "is_printing": false,
  "battery_level": 92
}
```

### Response Example (Cloud Relay Mode)
```json
{
  "status": "online",
  "connected": true,
  "mode": "relay",
  "group": "Counter-1",
  "client_name": "Store POS Terminal 1",
  "printer_name": "Bainiu X6",
  "is_printing": false,
  "battery_level": 85,
  "rssi": -45
}
```

---

## 17. Cloud Relay WebSocket Protocol (`/ws/client`)

Store client desktop applications connect to the cloud server via WebSocket:

```
Connection URL: wss://your-pos-server.com/ws/client?api_key=<CLIENT_KEY>&client_name=<TERMINAL_NAME>
```

### 1. Server Handshake (`welcome`)
```json
{
  "type": "welcome",
  "client_id": "client_8b3a12",
  "client_name": "Store Terminal 1",
  "group": "Cashier",
  "server_version": "1.0.0",
  "server_time": "2026-09-12T14:15:00Z"
}
```

### 2. Client Heartbeat (`ping` / `pong`)
Clients send a heartbeat ping every 15–30 seconds:
```json
{ "type": "ping" }
```
Server replies immediately:
```json
{ "type": "pong" }
```

### 3. Client Telemetry Report (`printer_status`)
Clients report their local thermal printer status and signal strength:
```json
{
  "type": "printer_status",
  "status": "online",
  "printer_name": "Bainiu X6",
  "battery_level": 88,
  "rssi": -42
}
```

### 4. Server Dispatches Print Job (`print_job`)
The cloud server delivers raster lines to the store client:
```json
{
  "type": "print_job",
  "job_id": "3da164e0-833f-4d7d-9f97-67115dbb1061",
  "job_type": "text",
  "data": "<BASE64_ENCODED_LSB_BITMAP>",
  "strength": 7,
  "width": 384,
  "height": 450
}
```

### 5. Server Dispatches Direct Hardware Command (`printer_command`)
```json
{
  "type": "printer_command",
  "command": "feed"
}
```

---

## 18. Best Practices & Production Deployment

1. **Database Bloat Protection (`keep_job=false`):**
   High-volume retail stores printing thousands of receipts per day will accumulate large SQLite databases. By default, `keep_job=false` purges temporary job records after 5 minutes while maintaining smooth streaming. Only pass `keep_job=true` if your accounting system requires historical PNG reprint raster inspection.
2. **Optimal Scaling Multipliers:**
   - Standard 58mm receipts: `scale=1.0` (384 dots).
   - 80mm receipts / invoices: `scale=1.25`.
   - A4 / Letter full invoices: `scale=1.5` with `autocrop=true`.
3. **Paper Tear Feeding:**
   Always invoke `POST /api/print/feed` after printing invoices or receipts so the bottom margin advances past the physical serrated tear cutter bar.
4. **Security:**
   - Always run behind HTTPS/TLS reverse proxy (e.g., Nginx, Caddy, Cloudflare).
   - Pass production proxy headers: `X-Forwarded-Proto: https` and `X-Forwarded-Host: your-domain.com`.
