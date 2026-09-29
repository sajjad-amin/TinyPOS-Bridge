# TinyPOS Mobile Client (`client-mobile`)

Cross-platform mobile application built with **Flutter (Dart)** for Android & iOS.

Acts both as a **portable Cloud Relay bridge** for your hosted TinyPOS server and as a **100% offline pocket thermal studio** with zero bloatware, zero ads, and zero account requirements.

---

## Key Features

1. **🔤 Universal Text & Notes Print**
   - Free-form text input supporting any language on Earth (English, Bengali, Arabic RTL, Chinese, Hindi, Japanese, Russian, etc.) and all emojis.
   - Text alignment (Left, Center, Right), font size selector, bold toggle, and darkness strength (1–7).

2. **🖼️ Photo & Artwork Studio**
   - Camera & Gallery photo picker.
   - **5 Quality Presets**: `Portrait` (soft skin tones), `Crisp & Detailed` (eyes, jewelry), `Balanced` (nature & landscapes), `High Contrast` (logos & ink art), and `Retro Halftone` (vintage newsprint).
   - **3 Dithering Algorithms**: Floyd-Steinberg, Bill Atkinson (Apple Mac classic), and Bayer 8x8 matrix.
   - Real-time **384px live thermal preview** before burning paper.
   - Edge sharpening (unsharp mask), contrast curve, brightness shadow lift, and auto-cropping of white borders.

3. **📱 Thermal QR Code Generator**
   - **3 Dedicated Modes**:
     - **Web URL**: e.g., `https://your-store.com`
     - **Wi-Fi Barcode**: Network SSID, Password, Encryption (WPA/WPA2, WEP, Open), and hidden network toggle.
     - **Plain Text**: Raw serial codes, crypto addresses, or data.
   - Optional **Header text** and **Footer text** printed above and below the QR code.

4. **📄 Direct Document & Invoice Print**
   - Direct picker for **PDF documents** (invoices, bills, receipts) and image files.
   - Automatically rasterizes PDF pages to high-resolution, auto-crops margins, and scales to 384 dots (57mm thermal rolls).

5. **☁️ Cloud Relay Bridge**
   - Connects to your hosted TinyPOS server via WebSocket (`wss://your-pos-server.com/ws/client?api_key=...`).
   - Receives print jobs in real-time from your cloud POS / web app and streams them to the nearby Bluetooth printer.
   - **1-Click Camera QR Pairing**: Tap "Scan Server QR Code", point camera at the web console, and connect instantly.

6. **🖨️ Hardware & Thermal Controls**
   - Bluetooth Low Energy (BLE) scanning, signal RSSI meter, auto-connect to closest printer.
   - Instant **Feed Paper** action button.

---

## Supported Thermal Printers

- **Bainiu / Tiny Print 57mm BLE Printers**: X6, X5, C9, MX0, iPrint, GB01, WalkPrint, and compatible pocket thermal printers.
- **Standard ESC/POS BLE Printers**: Any BLE thermal printer exposing standard service UUIDs `0xAE30`, `0xAF30`, or `0xFF00`.

---

## Running Locally

Ensure Flutter 3.x is installed:

```bash
cd client-mobile
flutter pub get
flutter run
```

### Testing & Code Verification

```bash
flutter analyze
flutter test
```
