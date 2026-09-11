/**
 * Photo & Artwork Studio client script.
 * Supports:
 * - Drag-and-drop & Clipboard Paste (Ctrl+V / Cmd+V)
 * - Live 384px thermal dot simulation
 * - Preset auto-tuning and fine-grained dithering / unsharp-mask controls
 * - Fullscreen preview and direct printing
 */

let livePreviewTimeout = null;
let currentPhotoBlobUrl = null;
let currentThermalBlobUrl = null;

function onPhotoPresetChange() {
    const preset = document.getElementById('photo-preset').value;
    const ditherSelect = document.getElementById('photo-dither');
    const sharpnessSelect = document.getElementById('photo-sharpness');
    const contrastSelect = document.getElementById('photo-contrast');
    const brightnessSelect = document.getElementById('photo-brightness');

    if (!ditherSelect || !sharpnessSelect) return;

    if (preset === 'portrait') {
        ditherSelect.value = 'floyd';
        sharpnessSelect.value = '1.2';
        contrastSelect.value = 'default';
        brightnessSelect.value = 'default';
    } else if (preset === 'sharp') {
        ditherSelect.value = 'atkinson';
        sharpnessSelect.value = '2.0';
        contrastSelect.value = 'default';
        brightnessSelect.value = 'default';
    } else if (preset === 'balanced') {
        ditherSelect.value = 'floyd';
        sharpnessSelect.value = '1.0';
        contrastSelect.value = '1.0';
        brightnessSelect.value = '1.0';
    } else if (preset === 'high_contrast') {
        ditherSelect.value = 'atkinson';
        sharpnessSelect.value = '1.5';
        contrastSelect.value = '1.30';
        brightnessSelect.value = '1.0';
    } else if (preset === 'halftone') {
        ditherSelect.value = 'bayer';
        sharpnessSelect.value = '1.0';
        contrastSelect.value = '1.15';
        brightnessSelect.value = '1.0';
    }

    triggerLivePhotoPreview();
}

function togglePhotoViewMode(mode) {
    const thermalImg = document.getElementById('photo-thermal-preview');
    const origImg = document.getElementById('photo-thumb');
    const btnThermal = document.getElementById('btn-view-thermal');
    const btnOrig = document.getElementById('btn-view-orig');

    if (mode === 'thermal') {
        thermalImg.classList.remove('d-none');
        origImg.classList.add('d-none');
        btnThermal.className = 'btn btn-primary fw-bold btn-sm py-0 px-2';
        btnOrig.className = 'btn btn-outline-secondary btn-sm py-0 px-2';
    } else {
        thermalImg.classList.add('d-none');
        origImg.classList.remove('d-none');
        btnThermal.className = 'btn btn-outline-secondary btn-sm py-0 px-2';
        btnOrig.className = 'btn btn-primary fw-bold btn-sm py-0 px-2';
    }
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function handlePhotoFile(file) {
    if (!file || !file.type.startsWith('image/')) {
        showToast('Please select a valid image file (JPG, PNG, WebP)', 'text-bg-warning');
        return;
    }

    const dropzone = document.getElementById('photo-dropzone');
    const previewBox = document.getElementById('photo-preview-box');
    const filenameEl = document.getElementById('photo-filename');
    const metaEl = document.getElementById('photo-meta');
    const thumbImg = document.getElementById('photo-thumb');

    filenameEl.textContent = file.name;
    metaEl.textContent = `${formatBytes(file.size)} • ${file.type.replace('image/', '').toUpperCase()}`;

    const reader = new FileReader();
    reader.onload = (e) => {
        thumbImg.src = e.target.result;
        dropzone.classList.add('d-none');
        previewBox.classList.remove('d-none');
        triggerLivePhotoPreview(true);
    };
    reader.readAsDataURL(file);
}

function triggerLivePhotoPreview(immediate = false) {
    if (livePreviewTimeout) clearTimeout(livePreviewTimeout);

    const delay = immediate ? 10 : 220;
    livePreviewTimeout = setTimeout(async () => {
        const formData = buildPhotoFormData();
        if (!formData) return;

        const spinner = document.getElementById('photo-preview-spinner');
        const thermalImg = document.getElementById('photo-thermal-preview');
        if (spinner) spinner.classList.remove('d-none');

        try {
            const res = await fetch('/api/internal/preview-photo', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                const blob = await res.blob();
                if (currentThermalBlobUrl) URL.revokeObjectURL(currentThermalBlobUrl);
                currentThermalBlobUrl = URL.createObjectURL(blob);
                thermalImg.src = currentThermalBlobUrl;
                togglePhotoViewMode('thermal');
            }
        } catch (e) {
            console.warn('Live photo preview error:', e);
        } finally {
            if (spinner) spinner.classList.add('d-none');
        }
    }, delay);
}

function initPhotoDropzone() {
    const dropzone = document.getElementById('photo-dropzone');
    const fileInput = document.getElementById('photo-file');

    if (!dropzone || !fileInput) return;

    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handlePhotoFile(fileInput.files[0]);
        }
    });

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
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('border-primary', 'bg-primary-subtle', 'shadow-sm');
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handlePhotoFile(e.dataTransfer.files[0]);
        }
    }, false);

    // Global / Window Clipboard Paste handler (Ctrl+V / Cmd+V)
    window.addEventListener('paste', (e) => {
        if (!e.clipboardData || !e.clipboardData.items) return;

        // Avoid intercepting paste if typing in a text area or input (like text tab or qr content)
        const activeTag = (document.activeElement?.tagName || '').toLowerCase();
        if (activeTag === 'textarea' || (activeTag === 'input' && document.activeElement?.type === 'text')) {
            return;
        }

        for (let i = 0; i < e.clipboardData.items.length; i++) {
            const item = e.clipboardData.items[i];
            if (item.type && item.type.startsWith('image/')) {
                const blob = item.getAsFile();
                if (blob) {
                    const ext = item.type.split('/')[1] || 'png';
                    const file = new File([blob], `pasted_photo_${Date.now()}.${ext}`, { type: item.type });

                    const dt = new DataTransfer();
                    dt.items.add(file);
                    fileInput.files = dt.files;
                    handlePhotoFile(file);
                    showToast('Pasted image loaded into Photo Studio!', 'text-bg-success');
                    e.preventDefault();
                    break;
                }
            }
        }
    });
}

function clearSelectedPhoto(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const fileInput = document.getElementById('photo-file');
    const dropzone = document.getElementById('photo-dropzone');
    const previewBox = document.getElementById('photo-preview-box');
    const thumbImg = document.getElementById('photo-thumb');
    const thermalImg = document.getElementById('photo-thermal-preview');

    if (fileInput) fileInput.value = '';
    if (thumbImg) thumbImg.src = '';
    if (thermalImg) thermalImg.src = '';
    if (currentThermalBlobUrl) {
        URL.revokeObjectURL(currentThermalBlobUrl);
        currentThermalBlobUrl = null;
    }
    if (previewBox) previewBox.classList.add('d-none');
    if (dropzone) dropzone.classList.remove('d-none');
}

function buildPhotoFormData() {
    const fileInput = document.getElementById('photo-file');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        return null;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('preset', document.getElementById('photo-preset').value);
    formData.append('dither_algo', document.getElementById('photo-dither').value);
    formData.append('sharpness', document.getElementById('photo-sharpness').value);
    formData.append('strength', document.getElementById('photo-strength').value);
    formData.append('scale', document.getElementById('photo-scale').value);
    formData.append('autocrop', document.getElementById('photo-autocrop').checked ? 'true' : 'false');

    const contrast = document.getElementById('photo-contrast').value;
    if (contrast !== 'default') formData.append('contrast', contrast);

    const brightness = document.getElementById('photo-brightness').value;
    if (brightness !== 'default') formData.append('brightness', brightness);

    return formData;
}

async function printPhotoNow() {
    const formData = buildPhotoFormData();
    if (!formData) {
        showToast('Please select, drop, or paste a photo to print', 'text-bg-warning');
        return;
    }

    const btnPrint = document.getElementById('btn-print-photo');
    const btnStop = document.getElementById('btn-stop-photo');
    if (btnPrint) btnPrint.disabled = true;
    if (btnStop) btnStop.disabled = false;

    showToast('Printing photo with high-fidelity thermal halftoning...');

    try {
        const res = await fetch('/api/internal/print-photo', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            showToast('Photo printed successfully with high-fidelity halftoning!', 'text-bg-success');
        } else {
            if (data.status === 'cancelled' || (data.message && data.message.toLowerCase().includes('stop'))) {
                showToast('Photo print job stopped.', 'text-bg-warning');
            } else {
                showToast(data.message || 'Photo print failed', 'text-bg-danger');
            }
        }
        loadQueue(1);
    } catch (e) {
        showToast('Photo upload failed: ' + e.message, 'text-bg-danger');
    } finally {
        if (btnPrint) btnPrint.disabled = false;
        if (btnStop) btnStop.disabled = true;
    }
}

function openPhotoModalPreview() {
    const thermalImg = document.getElementById('photo-thermal-preview');
    if (!thermalImg || !thermalImg.src) {
        showToast('Select or paste a photo first to view preview', 'text-bg-warning');
        return;
    }
    document.getElementById('preview-img').src = thermalImg.src;
    new bootstrap.Modal(document.getElementById('previewModal')).show();
}

// Auto-initialize photo dropzone on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPhotoDropzone);
} else {
    initPhotoDropzone();
}
