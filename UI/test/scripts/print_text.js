async function printTextNow() {
    const text = document.getElementById('receipt-text').value;
    const fontSize = parseInt(document.getElementById('font-size').value) || 22;
    const strength = parseInt(document.getElementById('print-strength').value) || 7;

    if (!text.trim()) {
        showToast('Please enter receipt text', 'text-bg-warning');
        return;
    }

    setPrintingUI(true, 'text');

    try {
        const res = await fetch('/api/internal/print-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, font_size: fontSize, strength: strength })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Print completed successfully (Strength ' + strength + ')!', 'text-bg-success');
        } else {
            if (data.status === 'cancelled' || (data.message && data.message.toLowerCase().includes('stop'))) {
                showToast('Print job was stopped.', 'text-bg-warning');
            } else {
                showToast(data.message || 'Print failed', 'text-bg-danger');
            }
        }
        loadQueue(1);
    } catch (e) {
        showToast('Print request failed: ' + e.message, 'text-bg-danger');
    } finally {
        setPrintingUI(false);
    }
}

async function previewTextBitmap() {
    const text = document.getElementById('receipt-text').value;
    const fontSize = parseInt(document.getElementById('font-size').value) || 22;
    const strength = parseInt(document.getElementById('print-strength').value) || 7;

    try {
        const res = await fetch('/api/internal/preview-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, font_size: fontSize, strength: strength })
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById('preview-img').src = url;
        new bootstrap.Modal(document.getElementById('previewModal')).show();
    } catch (e) {
        showToast('Preview error', 'text-bg-danger');
    }
}
