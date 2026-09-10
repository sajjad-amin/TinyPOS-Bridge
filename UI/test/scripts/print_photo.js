/**
 * Photo & Artwork Studio client script.
 * Handles photo drag-and-drop, dynamic thumbnail display, quality presets,
 * live 384px halftone simulation, and direct printing.
 */

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
}

function initPhotoDropzone() {
    const dropzone = document.getElementById('photo-dropzone');
    const fileInput = document.getElementById('photo-file');
    const promptEl = document.getElementById('photo-prompt');
    const previewBox = document.getElementById('photo-preview-box');
    const thumbImg = document.getElementById('photo-thumb');
    const filenameEl = document.getElementById('photo-filename');
    const metaEl = document.getElementById('photo-meta');

    if (!dropzone || !fileInput) return;

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function handleFile(file) {
        if (!file || !file.type.startsWith('image/')) {
            showToast('Please select a valid image file (JPG, PNG, WebP)', 'text-bg-warning');
            return;
        }

        filenameEl.textContent = file.name;
        metaEl.textContent = `${formatBytes(file.size)} • ${file.type.replace('image/', '').toUpperCase()}`;

        const reader = new FileReader();
        reader.onload = (e) => {
            thumbImg.src = e.target.result;
            promptEl.classList.add('d-none');
            previewBox.classList.remove('d-none');
            previewBox.classList.add('d-flex');
            dropzone.classList.add('border-warning', 'bg-warning-subtle');
        };
        reader.readAsDataURL(file);
    }

    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleFile(fileInput.files[0]);
        }
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('border-warning', 'bg-warning-subtle', 'shadow-sm');
        }, false);
    });

    ['dragleave', 'dragend'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('border-warning', 'bg-warning-subtle', 'shadow-sm');
            if (fileInput.files && fileInput.files.length > 0) {
                dropzone.classList.add('border-warning', 'bg-warning-subtle');
            }
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('border-warning', 'bg-warning-subtle', 'shadow-sm');
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handleFile(e.dataTransfer.files[0]);
        }
    }, false);
}

function clearSelectedPhoto(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const fileInput = document.getElementById('photo-file');
    const promptEl = document.getElementById('photo-prompt');
    const previewBox = document.getElementById('photo-preview-box');
    const thumbImg = document.getElementById('photo-thumb');
    const dropzone = document.getElementById('photo-dropzone');

    if (fileInput) fileInput.value = '';
    if (thumbImg) thumbImg.src = '';
    if (previewBox) {
        previewBox.classList.add('d-none');
        previewBox.classList.remove('d-flex');
    }
    if (promptEl) promptEl.classList.remove('d-none');
    if (dropzone) dropzone.classList.remove('border-warning', 'bg-warning-subtle');
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
        showToast('Please select or drop a photo to print', 'text-bg-warning');
        return;
    }

    const btnPrint = document.getElementById('btn-print-photo');
    const btnStop = document.getElementById('btn-stop-photo');
    if (btnPrint) btnPrint.disabled = true;
    if (btnStop) btnStop.disabled = false;

    showToast('Processing high-quality photo halftone...');

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

async function previewPhotoHalftone() {
    const formData = buildPhotoFormData();
    if (!formData) {
        showToast('Please select or drop a photo to preview', 'text-bg-warning');
        return;
    }

    showToast('Simulating 384px thermal halftone...');

    try {
        const res = await fetch('/api/internal/preview-photo', {
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

// Auto-initialize photo dropzone on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPhotoDropzone);
} else {
    initPhotoDropzone();
}
