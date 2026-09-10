async function printFileNow() {
    const fileInput = document.getElementById('receipt-file');
    const fileStrength = document.getElementById('file-strength').value || '7';
    const fileScale = document.getElementById('file-scale').value || '1.0';
    const fileAutocrop = document.getElementById('file-autocrop').checked ? 'true' : 'false';

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('Please select an invoice PDF or image file', 'text-bg-warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('strength', fileStrength);
    formData.append('scale', fileScale);
    formData.append('autocrop', fileAutocrop);

    setPrintingUI(true, 'file');

    try {
        const res = await fetch('/api/internal/print-file', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            showToast(`File printed successfully (Strength ${fileStrength}, Scale ${Math.round(fileScale*100)}%)!`, 'text-bg-success');
        } else {
            if (data.status === 'cancelled' || (data.message && data.message.toLowerCase().includes('stop'))) {
                showToast('Print job was stopped.', 'text-bg-warning');
            } else {
                showToast(data.message || 'File print failed', 'text-bg-danger');
            }
        }
        loadQueue(1);
    } catch (e) {
        showToast('Upload failed: ' + e.message, 'text-bg-danger');
    } finally {
        setPrintingUI(false);
    }
}

async function previewFileBitmap() {
    const fileInput = document.getElementById('receipt-file');
    const fileStrength = document.getElementById('file-strength').value || '7';
    const fileScale = document.getElementById('file-scale').value || '1.0';
    const fileAutocrop = document.getElementById('file-autocrop').checked ? 'true' : 'false';

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('Please select an invoice PDF or image file to preview', 'text-bg-warning');
        return;
    }

    showToast('Generating 384px bitmap preview...');
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('strength', fileStrength);
    formData.append('scale', fileScale);
    formData.append('autocrop', fileAutocrop);

    try {
        const res = await fetch('/api/internal/preview-file', {
            method: 'POST',
            body: formData
        });
        if (!res.ok) {
            const err = await res.text();
            showToast('Preview error: ' + err, 'text-bg-danger');
            return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById('preview-img').src = url;
        new bootstrap.Modal(document.getElementById('previewModal')).show();
    } catch (e) {
        showToast('Preview request failed: ' + e.message, 'text-bg-danger');
    }
}
