async function printFileNow() {
    const fileInput = document.getElementById('receipt-file');
    const fileStrength = document.getElementById('file-strength').value || '7';
    const fileScale = document.getElementById('file-scale').value || '1.0';
    const fileAutocrop = document.getElementById('file-autocrop').checked ? 'true' : 'false';
    const isPhotoMode = document.getElementById('file-photo-mode')?.checked;
    const fileMode = isPhotoMode ? 'photo' : 'text';

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('Please select an invoice PDF or image file', 'text-bg-warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('strength', fileStrength);
    formData.append('scale', fileScale);
    formData.append('autocrop', fileAutocrop);
    formData.append('mode', fileMode);
    formData.append('dither', isPhotoMode ? 'true' : 'false');

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
    const isPhotoMode = document.getElementById('file-photo-mode')?.checked;
    const fileMode = isPhotoMode ? 'photo' : 'text';

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('Please select an invoice PDF or image file to preview', 'text-bg-warning');
        return;
    }

    showToast(isPhotoMode ? 'Generating 384px dithered photo preview...' : 'Generating 384px bitmap preview...');
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('strength', fileStrength);
    formData.append('scale', fileScale);
    formData.append('autocrop', fileAutocrop);
    formData.append('mode', fileMode);
    formData.append('dither', isPhotoMode ? 'true' : 'false');

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

function initFileDropzone() {
    const dropzone = document.getElementById('file-dropzone');
    const fileInput = document.getElementById('receipt-file');
    const promptEl = document.getElementById('dropzone-prompt');
    const selectedEl = document.getElementById('dropzone-selected');
    const filenameEl = document.getElementById('dropzone-filename');
    const filesizeEl = document.getElementById('dropzone-filesize');

    if (!dropzone || !fileInput) return;

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function updateUI() {
        if (fileInput.files && fileInput.files.length > 0) {
            const f = fileInput.files[0];
            if (filenameEl) filenameEl.textContent = f.name;
            if (filesizeEl) filesizeEl.textContent = `${formatBytes(f.size)} • ${f.type || 'Document'}`;
            if (promptEl) promptEl.classList.add('d-none');
            if (selectedEl) {
                selectedEl.classList.remove('d-none');
                selectedEl.classList.add('d-flex');
            }
            dropzone.classList.add('border-primary', 'bg-body-secondary');
        } else {
            if (promptEl) promptEl.classList.remove('d-none');
            if (selectedEl) {
                selectedEl.classList.add('d-none');
                selectedEl.classList.remove('d-flex');
            }
            dropzone.classList.remove('border-primary', 'bg-body-secondary');
        }
    }

    fileInput.addEventListener('change', updateUI);

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('border-primary', 'bg-primary-subtle', 'shadow-sm');
        }, false);
    });

    ['dragleave', 'dragend'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('border-primary', 'bg-primary-subtle', 'shadow-sm');
            if (fileInput.files && fileInput.files.length > 0) {
                dropzone.classList.add('border-primary', 'bg-body-secondary');
            }
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('border-primary', 'bg-primary-subtle', 'shadow-sm');
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            updateUI();
        }
    }, false);
}

function clearSelectedFile(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const fileInput = document.getElementById('receipt-file');
    if (fileInput) {
        fileInput.value = '';
        fileInput.dispatchEvent(new Event('change'));
    }
}

// Auto-initialize dropzone on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFileDropzone);
} else {
    initFileDropzone();
}
