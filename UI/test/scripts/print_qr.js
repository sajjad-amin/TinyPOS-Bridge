function setQRPreset(type) {
    const contentEl = document.getElementById('qr-content');
    const headerEl = document.getElementById('qr-header');
    const footerEl = document.getElementById('qr-footer');
    if (!contentEl || !headerEl || !footerEl) return;

    if (type === 'url') {
        contentEl.value = 'https://pos.sayem.com';
        headerEl.value = 'SCAN TO VISIT';
        footerEl.value = 'https://pos.sayem.com';
    } else if (type === 'wifi') {
        contentEl.value = 'WIFI:S:TinyPOS_Guest;T:WPA;P:pos123456;;';
        headerEl.value = 'CONNECT TO WI-FI';
        footerEl.value = 'SSID: TinyPOS_Guest';
    } else if (type === 'upi') {
        contentEl.value = 'upi://pay?pa=merchant@pos&pn=TinyPOS%20Store&am=150.00&cu=INR';
        headerEl.value = 'SCAN TO PAY';
        footerEl.value = 'UPI Payment Accepted';
    } else if (type === 'text') {
        contentEl.value = 'Thank you for your visit! Table #12';
        headerEl.value = 'ORDER TICKET';
        footerEl.value = 'TinyPOS Thermal Bridge';
    }
}

async function printQRNow() {
    const content = document.getElementById('qr-content').value;
    const header = document.getElementById('qr-header').value;
    const footer = document.getElementById('qr-footer').value;
    const qrSize = parseInt(document.getElementById('qr-size').value) || 260;
    const strength = parseInt(document.getElementById('qr-strength').value) || 7;

    if (!content.trim()) {
        showToast('Please enter QR code content', 'text-bg-warning');
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
    const content = document.getElementById('qr-content').value;
    const header = document.getElementById('qr-header').value;
    const footer = document.getElementById('qr-footer').value;
    const qrSize = parseInt(document.getElementById('qr-size').value) || 260;
    const strength = parseInt(document.getElementById('qr-strength').value) || 7;

    if (!content.trim()) {
        showToast('Please enter QR code content to preview', 'text-bg-warning');
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
        showToast('QR Preview error', 'text-bg-danger');
    }
}
