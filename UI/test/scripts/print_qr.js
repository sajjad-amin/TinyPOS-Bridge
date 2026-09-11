/**
 * QR Code Printing and Preview Logic.
 * Supports URL, Wi-Fi (SSID, Password, Security), and Plain Text.
 */

let currentQRType = 'url';

function switchQRType(type) {
    currentQRType = type;
    const btnUrl = document.getElementById('qr-type-url');
    const btnWifi = document.getElementById('qr-type-wifi');
    const btnText = document.getElementById('qr-type-text');

    const paneUrl = document.getElementById('qr-pane-url');
    const paneWifi = document.getElementById('qr-pane-wifi');
    const paneText = document.getElementById('qr-pane-text');

    const headerEl = document.getElementById('qr-header');
    const footerEl = document.getElementById('qr-footer');

    // Reset button states
    [btnUrl, btnWifi, btnText].forEach(btn => {
        if (btn) btn.className = 'btn btn-outline-secondary btn-sm py-0 px-2';
    });
    // Hide all panels
    [paneUrl, paneWifi, paneText].forEach(pane => {
        if (pane) pane.classList.add('d-none');
    });

    if (type === 'url') {
        if (btnUrl) btnUrl.className = 'btn btn-primary btn-sm py-0 px-2 fw-semibold';
        if (paneUrl) paneUrl.classList.remove('d-none');
    } else if (type === 'wifi') {
        if (btnWifi) btnWifi.className = 'btn btn-primary btn-sm py-0 px-2 fw-semibold';
        if (paneWifi) paneWifi.classList.remove('d-none');
    } else if (type === 'text') {
        if (btnText) btnText.className = 'btn btn-primary btn-sm py-0 px-2 fw-semibold';
        if (paneText) paneText.classList.remove('d-none');
    }
}

// Backward compatibility alias
function setQRPreset(type) {
    switchQRType(type);
}

function onQRFieldChange() {
    // Left empty: no automatic header/footer overwrite
}

function getQRPayload() {
    if (currentQRType === 'url') {
        return (document.getElementById('qr-input-url')?.value || '').trim();
    } else if (currentQRType === 'wifi') {
        const ssid = (document.getElementById('qr-wifi-ssid')?.value || '').trim();
        const pass = document.getElementById('qr-wifi-pass')?.value || '';
        const sec = document.getElementById('qr-wifi-sec')?.value || 'WPA';
        if (!ssid) return '';
        if (sec === 'nopass' || !pass) {
            return `WIFI:S:${ssid};;`;
        }
        return `WIFI:S:${ssid};T:${sec};P:${pass};;`;
    } else {
        return (document.getElementById('qr-content')?.value || '').trim();
    }
}

async function printQRNow() {
    const content = getQRPayload();
    const header = document.getElementById('qr-header')?.value || '';
    const footer = document.getElementById('qr-footer')?.value || '';
    const qrSize = parseInt(document.getElementById('qr-size')?.value) || 260;
    const strength = parseInt(document.getElementById('qr-strength')?.value) || 7;

    if (!content) {
        if (currentQRType === 'wifi') {
            showToast('Please enter Wi-Fi Network Name (SSID)', 'text-bg-warning');
        } else {
            showToast('Please enter QR code content', 'text-bg-warning');
        }
        return;
    }

    setPrintingUI(true, 'qr');

    try {
        const res = await fetch('/api/internal/print-qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                header: header,
                footer: footer,
                qr_size: qrSize,
                strength: strength
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast('QR Code printed successfully (Strength ' + strength + ')!', 'text-bg-success');
        } else {
            if (data.status === 'cancelled' || (data.message && data.message.toLowerCase().includes('stop'))) {
                showToast('QR print job was stopped.', 'text-bg-warning');
            } else {
                showToast(data.message || 'QR print failed', 'text-bg-danger');
            }
        }
        loadQueue(1);
    } catch (e) {
        showToast('Print request failed: ' + e.message, 'text-bg-danger');
    } finally {
        setPrintingUI(false);
    }
}

async function previewQRBitmap() {
    const content = getQRPayload();
    const header = document.getElementById('qr-header')?.value || '';
    const footer = document.getElementById('qr-footer')?.value || '';
    const qrSize = parseInt(document.getElementById('qr-size')?.value) || 260;
    const strength = parseInt(document.getElementById('qr-strength')?.value) || 7;

    if (!content) {
        if (currentQRType === 'wifi') {
            showToast('Please enter Wi-Fi Network Name (SSID)', 'text-bg-warning');
        } else {
            showToast('Please enter QR code content to preview', 'text-bg-warning');
        }
        return;
    }

    try {
        const res = await fetch('/api/internal/preview-qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                header: header,
                footer: footer,
                qr_size: qrSize,
                strength: strength
            })
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById('preview-img').src = url;
        new bootstrap.Modal(document.getElementById('previewModal')).show();
    } catch (e) {
        showToast('QR Preview error: ' + e.message, 'text-bg-danger');
    }
}
