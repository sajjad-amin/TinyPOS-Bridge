// TinyPOS Playground Client Controller
const STORAGE_KEY_API = 'tinypos_api_key';
const STORAGE_KEY_SERVER = 'tinypos_server_url';

let pendingJobId = null;
let pollTimer = null;
let selectedDoc = null;
let selectedPhoto = null;
let currentQRMode = 'url';
let qrDebounce = null;
let configModalInstance = null;
let previewModalInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    // Bootstrap Modal instances
    const cfgModalEl = document.getElementById('configModal');
    if (cfgModalEl && window.bootstrap) {
        configModalInstance = new bootstrap.Modal(cfgModalEl);
    }
    const prevModalEl = document.getElementById('previewModal');
    if (prevModalEl && window.bootstrap) {
        previewModalInstance = new bootstrap.Modal(prevModalEl);
    }

    initTerminal();
    checkPrinterStatus(true);
    startStatusPolling();
    initClipboardPaste();
    initTabSwitcher();
});

// --- Configuration & Local Storage ---
function initTerminal() {
    let server = localStorage.getItem(STORAGE_KEY_SERVER);
    let key = localStorage.getItem(STORAGE_KEY_API);

    if (!server && window.location.protocol.startsWith('http')) {
        server = window.location.origin;
        localStorage.setItem(STORAGE_KEY_SERVER, server);
    }

    updateHeaderStatus(server, key);

    if (!key) {
        document.getElementById('setup-alert').classList.remove('d-none');
        document.getElementById('setup-alert').classList.add('d-flex');
        setTimeout(() => openConfigModal(), 400);
    }
}

function getServer() {
    let url = (localStorage.getItem(STORAGE_KEY_SERVER) || '').trim();
    if (!url && window.location.protocol.startsWith('http')) {
        url = window.location.origin;
    }
    return url.replace(/\/+$/, '');
}

function getKey() {
    return (localStorage.getItem(STORAGE_KEY_API) || '').trim();
}

function updateHeaderStatus(server, key) {
    const keyText = document.getElementById('nav-key-text');
    const keyBtn = document.getElementById('nav-key-btn');
    const alertBox = document.getElementById('setup-alert');

    if (key) {
        if (keyText) keyText.textContent = 'API Connected';
        if (keyBtn) {
            keyBtn.className = 'btn btn-outline-primary btn-sm rounded-pill px-2 px-sm-3 py-1 fw-semibold shadow-sm d-inline-flex align-items-center text-nowrap';
            keyBtn.innerHTML = '<i class="bi bi-shield-check text-success"></i> <span class="d-none d-sm-inline ms-1" id="nav-key-text">API Connected</span>';
        }
        if (alertBox) {
            alertBox.classList.add('d-none');
            alertBox.classList.remove('d-flex');
        }
    } else {
        if (keyText) keyText.textContent = 'Set API Key';
        if (keyBtn) {
            keyBtn.className = 'btn btn-warning btn-sm rounded-pill px-2 px-sm-3 py-1 fw-semibold shadow-sm d-inline-flex align-items-center text-nowrap';
            keyBtn.innerHTML = '<i class="bi bi-key-fill"></i> <span class="d-none d-sm-inline ms-1" id="nav-key-text">Set API Key</span>';
        }
        if (alertBox) {
            alertBox.classList.remove('d-none');
            alertBox.classList.add('d-flex');
        }
    }
}

function openConfigModal() {
    document.getElementById('cfg-server-url').value = getServer();
    document.getElementById('cfg-api-key').value = getKey();
    if (configModalInstance) {
        configModalInstance.show();
    }
}

function clearConfig() {
    localStorage.removeItem(STORAGE_KEY_API);
    localStorage.removeItem(STORAGE_KEY_SERVER);
    localStorage.removeItem('api_key');

    document.getElementById('cfg-api-key').value = '';
    document.getElementById('cfg-server-url').value = window.location.protocol.startsWith('http') ? window.location.origin : 'http://localhost:8100';

    updateHeaderStatus('', '');
    if (configModalInstance) configModalInstance.hide();
    showToast('Printer connection removed & local storage cleared', 'info');
    checkPrinterStatus(false);
}

function saveConfig() {
    let srv = document.getElementById('cfg-server-url').value.trim();
    const key = document.getElementById('cfg-api-key').value.trim();

    if (!key) {
        return showToast('Please enter your Printing API Key', 'warning');
    }

    if (!srv) {
        srv = window.location.protocol.startsWith('http') ? window.location.origin : 'http://localhost:8100';
    }
    srv = srv.replace(/\/+$/, '');

    localStorage.setItem(STORAGE_KEY_SERVER, srv);
    localStorage.setItem(STORAGE_KEY_API, key);

    updateHeaderStatus(srv, key);
    if (configModalInstance) configModalInstance.hide();
    showToast('Settings saved! Connecting to printer...', 'success');
    checkPrinterStatus(true);
}

// --- Live Printer Status Probing ---
async function checkPrinterStatus(isManual = false) {
    const srv = getServer();
    const key = getKey();

    const pill = document.getElementById('printer-pill');
    const title = document.getElementById('printer-title');
    const desc = document.getElementById('printer-desc');
    const stopBtn = document.getElementById('btn-stop');
    const battBadge = document.getElementById('printer-battery-badge');
    const battVal = document.getElementById('printer-battery-val');
    const iconBox = document.getElementById('printer-icon-box');
    const icon = document.getElementById('printer-icon');

    if (!srv || !key) {
        pill.className = 'badge bg-warning-subtle text-warning-emphasis';
        pill.innerHTML = '<i class="bi bi-key-fill me-1"></i> Key Required';
        title.textContent = 'API Key Required';
        desc.textContent = 'Click "Configure Key" to connect your printer terminal.';
        if (iconBox) iconBox.className = 'p-2 p-sm-3 bg-secondary-subtle text-secondary rounded-4 me-2 me-sm-3 d-flex align-items-center justify-content-center shadow-sm flex-shrink-0';
        if (icon) icon.className = 'bi bi-key-fill fs-4 fs-sm-3 text-warning';
        if (battBadge) battBadge.classList.add('d-none');
        const modeBadge = document.getElementById('printer-mode-badge');
        if (modeBadge) modeBadge.classList.add('d-none');
        stopBtn.disabled = true;
        return;
    }

    try {
        const res = await fetch(`${srv}/api/status?api_key=${encodeURIComponent(key)}`, {
            headers: { 'X-API-Key': key }
        });

        if (!res.ok) {
            let detail = `Server rejected API key (${res.status})`;
            try {
                const errData = await res.json();
                if (errData.detail) detail = errData.detail;
            } catch (_) {}
            pill.className = 'badge bg-danger-subtle text-danger-emphasis';
            pill.innerHTML = '<i class="bi bi-shield-x me-1"></i> Unauthorized';
            title.textContent = 'Unauthorized';
            desc.textContent = detail;
            stopBtn.disabled = true;
            return;
        }

        const data = await res.json();
        const isPrinting = data.is_printing === true || data.status === 'printing';
        const isOnline = data.status === 'online' || data.status === 'connected' || data.connected === true || data.online === true || isPrinting;

        stopBtn.disabled = !isPrinting;

        if (data.battery_level != null) {
            battBadge.classList.remove('d-none');
            battVal.textContent = `${data.battery_level}%`;
        } else {
            battBadge.classList.add('d-none');
        }

        const modeBadge = document.getElementById('printer-mode-badge');
        const modeText = document.getElementById('printer-mode-text');
        if (modeBadge && modeText) {
            modeBadge.classList.remove('d-none');
            modeText.textContent = data.mode === 'relay' ? 'Cloud Relay' : 'Direct BLE';
        }

        if (isPrinting) {
            pill.className = 'badge rounded-pill bg-primary-subtle text-primary border border-primary-subtle d-inline-flex align-items-center px-3 py-1';
            pill.innerHTML = '<span class="status-dot-blue me-2"></span> Printing...';
            title.textContent = data.printer_name || 'Thermal Printer (Printing)';
            desc.textContent = data.message || 'Actively streaming dot matrix raster to printer';
            iconBox.className = 'p-3 bg-primary-subtle text-primary rounded-4 me-3 d-flex align-items-center justify-content-center shadow-sm';
            icon.className = 'bi bi-printer-fill fs-3';
        } else if (isOnline) {
            pill.className = 'badge rounded-pill bg-success-subtle text-success-emphasis border border-success-subtle d-inline-flex align-items-center px-3 py-1';
            pill.innerHTML = '<span class="status-dot-green me-2"></span> Online';
            title.textContent = data.printer_name || 'Thermal POS Printer';
            if (data.mode === 'relay') {
                const clientName = data.active_client ? (data.active_client.client_name || data.active_client.ip) : (data.client_name || data.group || 'Active');
                desc.textContent = data.message || `Cloud Relay connected (${clientName})`;
                iconBox.className = 'p-3 bg-success-subtle text-success rounded-4 me-3 d-flex align-items-center justify-content-center shadow-sm';
                icon.className = 'bi bi-cloud-check-fill fs-3';
            } else {
                desc.textContent = data.message || (data.address ? `Bluetooth LE connected (${data.address})` : 'Direct Bluetooth LE connected');
                iconBox.className = 'p-3 bg-success-subtle text-success rounded-4 me-3 d-flex align-items-center justify-content-center shadow-sm';
                icon.className = 'bi bi-bluetooth fs-3';
            }
        } else {
            pill.className = 'badge rounded-pill bg-danger-subtle text-danger-emphasis border border-danger-subtle d-inline-flex align-items-center px-3 py-1';
            pill.innerHTML = '<span class="status-dot-red me-2"></span> Offline';
            title.textContent = data.printer_name || 'Printer Offline';
            desc.textContent = data.message || 'Printer offline. Ensure relay client or Bluetooth is connected.';
            iconBox.className = 'p-3 bg-secondary-subtle text-secondary rounded-4 me-3 d-flex align-items-center justify-content-center shadow-sm';
            icon.className = 'bi bi-printer fs-3';
        }

        if (isManual) {
            showToast(`Printer status: ${pill.textContent.trim()}`, isOnline ? 'success' : 'warning');
        }
    } catch (e) {
        pill.className = 'badge bg-danger-subtle text-danger-emphasis';
        pill.innerHTML = '<i class="bi bi-wifi-off me-1"></i> Disconnected';
        title.textContent = 'Server Unreachable';
        desc.textContent = `Cannot connect to server at ${srv} (${e.message})`;
        stopBtn.disabled = true;
    }
}

function startStatusPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
        if (document.visibilityState === 'visible') {
            checkPrinterStatus(false);
        }
    }, 5000);
}

// --- Feed & Stop ---
async function feedPaper() {
    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    try {
        const res = await fetch(`${srv}/api/print/feed?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key }
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Paper feed signal sent!', 'success');
        } else {
            showToast(data.detail || data.message || 'Paper feed failed', 'error');
        }
    } catch (e) {
        showToast('Feed error: ' + e.message, 'error');
    }
}

async function emergencyStop() {
    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    try {
        const res = await fetch(`${srv}/api/print/stop?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key }
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Emergency stop command dispatched', 'warning');
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'Stop failed', 'error');
        }
    } catch (e) {
        showToast('Stop error: ' + e.message, 'error');
    }
}

// --- Section 1: Text Printing ---
async function printText() {
    const text = document.getElementById('text-input').value;
    if (!text.trim()) return showToast('Please enter text to print', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const fontSize = parseInt(document.getElementById('text-font-size').value) || 22;
    const strength = parseInt(document.getElementById('text-strength').value) || 4;
    const btn = document.getElementById('btn-print-text');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing...';

    try {
        const res = await fetch(`${srv}/api/print/text?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': key
            },
            body: JSON.stringify({
                text: text,
                font_size: fontSize,
                strength: strength,
                immediate: true
            })
        });

        const data = await res.json();
        if (res.ok) {
            showToast('Receipt printed successfully!', 'success');
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'Print text failed', 'error');
        }
    } catch (e) {
        showToast('Print request error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print Text';
    }
}

async function previewText() {
    const text = document.getElementById('text-input').value;
    if (!text.trim()) return showToast('Please enter text to preview', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const fontSize = parseInt(document.getElementById('text-font-size').value) || 22;
    const strength = parseInt(document.getElementById('text-strength').value) || 4;

    try {
        showToast('Rendering preview...', 'info');
        const res = await fetch(`${srv}/api/print/text?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': key
            },
            body: JSON.stringify({
                text: text,
                font_size: fontSize,
                strength: strength,
                immediate: false
            })
        });

        const data = await res.json();
        if (res.ok && data.job_id) {
            openPreviewModal(`${srv}/api/print/preview/${data.job_id}?api_key=${encodeURIComponent(key)}`, data.job_id);
        } else {
            showToast(data.detail || 'Preview generation failed', 'error');
        }
    } catch (e) {
        showToast('Preview error: ' + e.message, 'error');
    }
}

// --- Section 2: QR Code ---
function setQRMode(mode) {
    currentQRMode = mode;
    document.getElementById('qr-btn-url').className = mode === 'url' ? 'btn btn-primary' : 'btn btn-outline-secondary';
    document.getElementById('qr-btn-wifi').className = mode === 'wifi' ? 'btn btn-primary' : 'btn btn-outline-secondary';
    document.getElementById('qr-btn-text').className = mode === 'text' ? 'btn btn-primary' : 'btn btn-outline-secondary';

    document.getElementById('qr-box-url').style.display = mode === 'url' ? 'block' : 'none';
    document.getElementById('qr-box-wifi').style.display = mode === 'wifi' ? 'block' : 'none';
    document.getElementById('qr-box-text').style.display = mode === 'text' ? 'block' : 'none';

    updateLiveQR();
}

function getQRText() {
    if (currentQRMode === 'url') {
        return document.getElementById('qr-input-url').value.trim();
    } else if (currentQRMode === 'wifi') {
        const ssid = document.getElementById('qr-wifi-ssid').value.trim();
        const pass = document.getElementById('qr-wifi-pass').value.trim();
        const sec = document.getElementById('qr-wifi-sec').value;
        if (!ssid) return '';
        return `WIFI:S:${ssid};T:${sec};P:${pass};;`;
    } else {
        return document.getElementById('qr-input-text').value.trim();
    }
}

function updateLiveQR() {
    clearTimeout(qrDebounce);
    qrDebounce = setTimeout(() => {
        const text = getQRText();
        const box = document.getElementById('qr-live-preview-box');
        const img = document.getElementById('qr-live-preview-img');
        const srv = getServer();
        const key = getKey();

        if (!text || !srv || !key) {
            box.style.display = 'none';
            return;
        }

        const header = document.getElementById('qr-header').value.trim();
        const footer = document.getElementById('qr-footer').value.trim();
        const size = document.getElementById('qr-size').value;

        const params = new URLSearchParams({
            api_key: key,
            text: text,
            size: size
        });
        if (header) params.append('header', header);
        if (footer) params.append('footer', footer);

        img.src = `${srv}/api/qr/generate?${params.toString()}`;
        box.style.display = 'block';
    }, 300);
}

async function printQR() {
    const content = getQRText();
    if (!content) return showToast('Please enter QR content/URL', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const header = document.getElementById('qr-header').value.trim() || null;
    const footer = document.getElementById('qr-footer').value.trim() || null;
    const size = parseInt(document.getElementById('qr-size').value) || 260;
    const strength = parseInt(document.getElementById('qr-strength').value) || 4;
    const btn = document.getElementById('btn-print-qr');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing...';

    try {
        const res = await fetch(`${srv}/api/print/qr?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': key
            },
            body: JSON.stringify({
                content: content,
                header: header,
                footer: footer,
                qr_size: size,
                strength: strength,
                immediate: true
            })
        });

        const data = await res.json();
        if (res.ok) {
            showToast('QR code printed successfully!', 'success');
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'QR print failed', 'error');
        }
    } catch (e) {
        showToast('QR print error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print QR Code';
    }
}

function previewQR() {
    const content = getQRText();
    if (!content) return showToast('Please enter QR content first', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const header = document.getElementById('qr-header').value.trim();
    const footer = document.getElementById('qr-footer').value.trim();
    const size = document.getElementById('qr-size').value;

    const params = new URLSearchParams({
        api_key: key,
        text: content,
        size: size
    });
    if (header) params.append('header', header);
    if (footer) params.append('footer', footer);

    openPreviewModal(`${srv}/api/qr/generate?${params.toString()}`, null);
}

// --- Section 3: Documents & Invoices ---
function handleDocSelected(files) {
    if (!files || !files.length) return;
    selectedDoc = files[0];

    document.getElementById('doc-file-name').textContent = selectedDoc.name;
    document.getElementById('doc-file-size').textContent = `${(selectedDoc.size / 1024).toFixed(1)} KB`;
    document.getElementById('doc-dropzone').style.display = 'none';
    const box = document.getElementById('doc-selected-box');
    box.style.display = 'flex';
}

function clearDocFile() {
    selectedDoc = null;
    document.getElementById('doc-file-input').value = '';
    document.getElementById('doc-selected-box').style.display = 'none';
    document.getElementById('doc-dropzone').style.display = 'flex';
}

async function printDoc() {
    if (!selectedDoc) return showToast('Please select a document or invoice to print', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const scale = document.getElementById('doc-scale').value;
    const strength = document.getElementById('doc-strength').value || '4';
    const autocrop = document.getElementById('doc-autocrop').checked;
    const btn = document.getElementById('btn-print-doc');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing...';

    const fd = new FormData();
    fd.append('file', selectedDoc);
    fd.append('scale', scale);
    fd.append('strength', strength);
    fd.append('autocrop', autocrop ? 'true' : 'false');
    fd.append('immediate', 'true');

    try {
        const res = await fetch(`${srv}/api/print/raw?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key },
            body: fd
        });

        const data = await res.json();
        if (res.ok) {
            showToast('Document printed successfully!', 'success');
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'Document print failed', 'error');
        }
    } catch (e) {
        showToast('Document print error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print Document';
    }
}

async function previewDoc() {
    if (!selectedDoc) return showToast('Please select a document to preview', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const scale = document.getElementById('doc-scale').value;
    const strength = document.getElementById('doc-strength').value || '4';
    const autocrop = document.getElementById('doc-autocrop').checked;

    const fd = new FormData();
    fd.append('file', selectedDoc);
    fd.append('scale', scale);
    fd.append('strength', strength);
    fd.append('autocrop', autocrop ? 'true' : 'false');
    fd.append('immediate', 'false');

    try {
        showToast('Rendering document raster...', 'info');
        const res = await fetch(`${srv}/api/print/raw?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key },
            body: fd
        });

        const data = await res.json();
        if (res.ok && data.job_id) {
            openPreviewModal(`${srv}/api/print/preview/${data.job_id}?api_key=${encodeURIComponent(key)}`, data.job_id);
        } else {
            showToast(data.detail || 'Document preview failed', 'error');
        }
    } catch (e) {
        showToast('Preview error: ' + e.message, 'error');
    }
}

// --- Section 4: Photo Studio ---
function handlePhotoSelected(files) {
    if (!files || !files.length) return;
    const f = files[0];
    if (!f.type.startsWith('image/')) return showToast('Only image files are supported', 'warning');

    selectedPhoto = f;
    document.getElementById('photo-file-name').textContent = f.name;
    document.getElementById('photo-file-size').textContent = `${(f.size / 1024).toFixed(1)} KB`;

    const r = new FileReader();
    r.onload = e => {
        document.getElementById('photo-preview-thumb').src = e.target.result;
        document.getElementById('photo-dropzone').style.display = 'none';
        document.getElementById('photo-selected-box').style.display = 'block';
    };
    r.readAsDataURL(f);
}

function clearPhotoFile() {
    selectedPhoto = null;
    document.getElementById('photo-file-input').value = '';
    document.getElementById('photo-selected-box').style.display = 'none';
    document.getElementById('photo-dropzone').style.display = 'flex';
}

function onPhotoPresetChange() {
    const preset = document.getElementById('photo-preset').value;
    const dither = document.getElementById('photo-dither');
    const sharp = document.getElementById('photo-sharpness');

    if (preset === 'portrait') {
        dither.value = 'floyd';
        sharp.value = '1.2';
    } else if (preset === 'sharp') {
        dither.value = 'floyd';
        sharp.value = '2.0';
    } else if (preset === 'halftone') {
        dither.value = 'bayer';
        sharp.value = '1.2';
    }
}

async function printPhoto() {
    if (!selectedPhoto) return showToast('Please select a photo to print', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const preset = document.getElementById('photo-preset').value;
    const dither = document.getElementById('photo-dither').value;
    const sharpness = document.getElementById('photo-sharpness').value;
    const strength = document.getElementById('photo-strength').value || '7';
    const contrast = document.getElementById('photo-contrast').value;
    const brightness = document.getElementById('photo-brightness').value;
    const autocrop = document.getElementById('photo-autocrop').checked;
    const btn = document.getElementById('btn-print-photo');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Halftoning & Printing...';

    const fd = new FormData();
    fd.append('file', selectedPhoto);
    fd.append('preset', preset);
    fd.append('dither_algo', dither);
    fd.append('sharpness', sharpness);
    fd.append('strength', strength);
    if (contrast !== 'default') fd.append('contrast', contrast);
    if (brightness !== 'default') fd.append('brightness', brightness);
    fd.append('autocrop', autocrop ? 'true' : 'false');
    fd.append('immediate', 'true');

    try {
        const res = await fetch(`${srv}/api/print/photo?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key },
            body: fd
        });

        const data = await res.json();
        if (res.ok) {
            showToast('Photo printed successfully with halftoning!', 'success');
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'Photo print failed', 'error');
        }
    } catch (e) {
        showToast('Photo print error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print Photo Now';
    }
}

async function previewPhoto() {
    if (!selectedPhoto) return showToast('Please select a photo to preview', 'warning');

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const preset = document.getElementById('photo-preset').value;
    const dither = document.getElementById('photo-dither').value;
    const sharpness = document.getElementById('photo-sharpness').value;
    const strength = document.getElementById('photo-strength').value || '7';
    const contrast = document.getElementById('photo-contrast').value;
    const brightness = document.getElementById('photo-brightness').value;
    const autocrop = document.getElementById('photo-autocrop').checked;

    const fd = new FormData();
    fd.append('file', selectedPhoto);
    fd.append('preset', preset);
    fd.append('dither_algo', dither);
    fd.append('sharpness', sharpness);
    fd.append('strength', strength);
    if (contrast !== 'default') fd.append('contrast', contrast);
    if (brightness !== 'default') fd.append('brightness', brightness);
    fd.append('autocrop', autocrop ? 'true' : 'false');
    fd.append('immediate', 'false');

    try {
        showToast('Rendering halftoned preview...', 'info');
        const res = await fetch(`${srv}/api/print/photo?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key },
            body: fd
        });

        const data = await res.json();
        if (res.ok && data.job_id) {
            openPreviewModal(`${srv}/api/print/preview/${data.job_id}?api_key=${encodeURIComponent(key)}`, data.job_id);
        } else {
            showToast(data.detail || 'Photo preview failed', 'error');
        }
    } catch (e) {
        showToast('Preview error: ' + e.message, 'error');
    }
}

// --- Preview Modal & Confirm ---
function openPreviewModal(imgUrl, jobId) {
    pendingJobId = jobId;
    const img = document.getElementById('preview-modal-img');
    const confirmBtn = document.getElementById('btn-modal-confirm');

    img.src = imgUrl;
    confirmBtn.style.display = jobId ? 'inline-block' : 'none';

    if (previewModalInstance) {
        previewModalInstance.show();
    }
}

async function confirmPrintModal() {
    if (!pendingJobId) return;

    const srv = getServer();
    const key = getKey();
    if (!key) return openConfigModal();

    const btn = document.getElementById('btn-modal-confirm');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing...';

    try {
        const res = await fetch(`${srv}/api/print/confirm/${pendingJobId}?api_key=${encodeURIComponent(key)}`, {
            method: 'POST',
            headers: { 'X-API-Key': key }
        });

        const data = await res.json();
        if (res.ok) {
            showToast('Print dispatched to thermal head!', 'success');
            if (previewModalInstance) previewModalInstance.hide();
            checkPrinterStatus(false);
        } else {
            showToast(data.detail || data.message || 'Confirm failed', 'error');
        }
    } catch (e) {
        showToast('Confirm error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Confirm &amp; Print';
    }
}

// --- Toast Feedback ---
function showToast(message, type = 'info') {
    const toastEl = document.getElementById('action-toast');
    const msgEl = document.getElementById('toast-message');
    if (!toastEl || !msgEl) return;

    msgEl.textContent = message;

    toastEl.className = 'toast align-items-center text-white border-0 shadow';
    if (type === 'success') toastEl.classList.add('bg-success');
    else if (type === 'error' || type === 'danger') toastEl.classList.add('bg-danger');
    else if (type === 'warning') toastEl.classList.add('bg-warning', 'text-dark');
    else toastEl.classList.add('bg-primary');

    if (window.bootstrap) {
        const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
        toast.show();
    }
}

// --- Clipboard & Tabs ---
function initClipboardPaste() {
    window.addEventListener('paste', e => {
        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const blob = items[i].getAsFile();
                handlePhotoSelected([blob]);
                showToast('Pasted image into Photo Studio!', 'info');
                break;
            }
        }
    });
}

function initTabSwitcher() {
    const tabBtns = document.querySelectorAll('#print-type-tabs button[data-bs-toggle]');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            tabBtns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            this.classList.add('active');
            this.setAttribute('aria-selected', 'true');
            const targetSelector = this.getAttribute('data-bs-target');
            document.querySelectorAll('#print-tab-content > .tab-pane').forEach(pane => {
                pane.classList.remove('active');
            });
            const targetPane = document.querySelector(targetSelector);
            if (targetPane) targetPane.classList.add('active');

            if (targetSelector === '#tab-qr-pane') {
                updateLiveQR();
            }
        });
    });
}
