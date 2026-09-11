function setPrintingUI(isPrinting, source = null) {
    const btnPrintText = document.getElementById('btn-print-text');
    const btnStopText = document.getElementById('btn-stop-text');
    const btnPrintQR = document.getElementById('btn-print-qr');
    const btnStopQR = document.getElementById('btn-stop-qr');
    const btnPrintFile = document.getElementById('btn-print-file');
    const btnStopFile = document.getElementById('btn-stop-file');

    if (isPrinting) {
        if (source === 'text') {
            if (btnPrintText) {
                btnPrintText.disabled = true;
                btnPrintText.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing...';
            }
            if (btnStopText) {
                btnStopText.disabled = false;
                btnStopText.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopText.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop Printing';
            }
            if (btnPrintQR) btnPrintQR.disabled = true;
            if (btnStopQR) {
                btnStopQR.disabled = false;
                btnStopQR.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
            }
            if (btnPrintFile) btnPrintFile.disabled = true;
            if (btnStopFile) {
                btnStopFile.disabled = false;
                btnStopFile.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopFile.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
        } else if (source === 'qr') {
            if (btnPrintQR) {
                btnPrintQR.disabled = true;
                btnPrintQR.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing QR...';
            }
            if (btnStopQR) {
                btnStopQR.disabled = false;
                btnStopQR.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopQR.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop Printing';
            }
            if (btnPrintText) btnPrintText.disabled = true;
            if (btnStopText) {
                btnStopText.disabled = false;
                btnStopText.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
            }
            if (btnPrintFile) btnPrintFile.disabled = true;
            if (btnStopFile) {
                btnStopFile.disabled = false;
                btnStopFile.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopFile.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
        } else if (source === 'file') {
            if (btnPrintFile) {
                btnPrintFile.disabled = true;
                btnPrintFile.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Processing & Printing...';
            }
            if (btnStopFile) {
                btnStopFile.disabled = false;
                btnStopFile.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopFile.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop Printing';
            }
            if (btnPrintText) btnPrintText.disabled = true;
            if (btnStopText) {
                btnStopText.disabled = false;
                btnStopText.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopText.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
            if (btnPrintQR) btnPrintQR.disabled = true;
            if (btnStopQR) {
                btnStopQR.disabled = false;
                btnStopQR.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
            }
        } else {
            if (btnPrintText) btnPrintText.disabled = true;
            if (btnPrintQR) btnPrintQR.disabled = true;
            if (btnPrintFile) btnPrintFile.disabled = true;
            if (btnStopText) {
                btnStopText.disabled = false;
                btnStopText.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopText.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
            if (btnStopQR) {
                btnStopQR.disabled = false;
                btnStopQR.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopQR.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
            if (btnStopFile) {
                btnStopFile.disabled = false;
                btnStopFile.className = 'btn btn-sm btn-danger px-3 fw-semibold shadow-sm';
                btnStopFile.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Stop';
            }
        }
    } else {
        if (btnPrintText) {
            btnPrintText.disabled = false;
            btnPrintText.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print Text';
        }
        if (btnStopText) {
            btnStopText.disabled = true;
            btnStopText.className = 'btn btn-sm btn-outline-danger px-3 fw-semibold';
            btnStopText.innerHTML = '<i class="bi bi-stop-circle me-1"></i> Stop';
        }
        if (btnPrintQR) {
            btnPrintQR.disabled = false;
            btnPrintQR.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print QR Code';
        }
        if (btnStopQR) {
            btnStopQR.disabled = true;
            btnStopQR.className = 'btn btn-sm btn-outline-danger px-3 fw-semibold';
            btnStopQR.innerHTML = '<i class="bi bi-stop-circle me-1"></i> Stop';
        }
        if (btnPrintFile) {
            btnPrintFile.disabled = false;
            btnPrintFile.innerHTML = '<i class="bi bi-printer-fill me-1"></i> Print File Now';
        }
        if (btnStopFile) {
            btnStopFile.disabled = true;
            btnStopFile.className = 'btn btn-sm btn-outline-danger px-3 fw-semibold';
            btnStopFile.innerHTML = '<i class="bi bi-stop-circle me-1"></i> Stop';
        }
    }
}

async function stopPrintingNow() {
    const btnStopText = document.getElementById('btn-stop-text');
    const btnStopQR = document.getElementById('btn-stop-qr');
    const btnStopFile = document.getElementById('btn-stop-file');

    if (btnStopText) {
        btnStopText.disabled = true;
        btnStopText.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Stopping...';
    }
    if (btnStopQR) {
        btnStopQR.disabled = true;
        btnStopQR.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Stopping...';
    }
    if (btnStopFile) {
        btnStopFile.disabled = true;
        btnStopFile.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Stopping...';
    }

    showToast('Sending stop command to printer...', 'text-bg-warning');

    try {
        const res = await fetch('/api/internal/stop', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Print job stopped successfully!', 'text-bg-warning');
        } else {
            showToast(data.message || 'Could not stop printer', 'text-bg-secondary');
        }
    } catch (e) {
        showToast('Failed to send stop command: ' + e.message, 'text-bg-danger');
    } finally {
        setTimeout(() => {
            setPrintingUI(false);
            loadQueue(currentPage);
        }, 300);
    }
}

async function stopJob(jobId) {
    showToast(`Stopping job ${jobId.substring(0, 8)}...`, 'text-bg-warning');
    try {
        const res = await fetch(`/api/internal/jobs/${jobId}/stop`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Job stopped!', 'text-bg-warning');
        } else {
            showToast(data.message || 'Could not stop job', 'text-bg-danger');
        }
    } catch (e) {
        showToast('Error stopping job: ' + e.message, 'text-bg-danger');
    } finally {
        setPrintingUI(false);
        loadQueue(currentPage);
    }
}

async function checkPrinterStatus(interactive = false) {
    const nameEl = document.getElementById('printer-name');
    const badgeEl = document.getElementById('printer-badge');
    const addrEl = document.getElementById('printer-address');
    const icon = document.getElementById('refresh-icon');
    const scanBtnText = document.getElementById('scan-btn-text');
    const printerIcon = document.getElementById('printer-icon');
    const printerIconBox = document.getElementById('printer-icon-box');

    if (icon) icon.classList.add('bi-spin');
    badgeEl.className = 'badge bg-warning-subtle text-warning';
    badgeEl.innerText = 'Checking...';

    try {
        const res = await fetch('/api/internal/status');
        const data = await res.json();
        const isRelay = data.mode === 'relay';

        if (scanBtnText) {
            scanBtnText.innerText = isRelay ? 'Check Relay Status' : 'Scan BLE Printer';
        }

        if (isRelay) {
            if (printerIcon) printerIcon.className = 'bi bi-cloud-arrow-up fs-3';
            if (printerIconBox) printerIconBox.className = 'p-3 bg-success-subtle text-success rounded-3';

            if (data.status === 'online') {
                if (data.is_printing) {
                    badgeEl.className = 'badge bg-primary-subtle text-primary';
                    badgeEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Relaying Print';
                    nameEl.innerText = data.printer_name || 'Store POS Client (Printing)';
                    setPrintingUI(true);
                } else {
                    badgeEl.className = 'badge bg-success-subtle text-success-emphasis';
                    badgeEl.innerHTML = '<i class="bi bi-cloud-check-fill me-1 small"></i> Relay Connected';
                    nameEl.innerText = data.printer_name || 'Store POS Client';
                }
                addrEl.innerText = data.address || 'WebSocket Connected';
                if (interactive) showToast('Store client is online: ' + (data.printer_name || 'Connected'), 'text-bg-success');
            } else {
                badgeEl.className = 'badge bg-warning-subtle text-warning-emphasis';
                badgeEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-1 small"></i> No Client Connected';
                nameEl.innerText = 'Cloud Relay Active (Waiting for Client)';
                addrEl.innerHTML = 'Direct BLE is disabled on server. Run client software on store PC (<a href="/settings" class="text-decoration-none">Settings</a>)';
                if (interactive) showToast('Cloud Relay: No store client connected. Please run client software.', 'text-bg-warning');
            }
        } else {
            // Direct Bluetooth Mode
            if (printerIcon) printerIcon.className = 'bi bi-bluetooth fs-3';
            if (printerIconBox) printerIconBox.className = 'p-3 bg-primary-subtle text-primary rounded-3';

            if (data.status === 'online') {
                if (data.is_printing) {
                    badgeEl.className = 'badge bg-primary-subtle text-primary';
                    badgeEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Printing';
                    nameEl.innerText = data.printer_name || 'X6 Thermal Printer (Printing)';
                    setPrintingUI(true);
                } else {
                    badgeEl.className = 'badge bg-success-subtle text-success-emphasis';
                    badgeEl.innerHTML = '<i class="bi bi-circle-fill me-1 small"></i> Online';
                    nameEl.innerText = data.printer_name || 'X6 Thermal Printer';
                }
                addrEl.innerText = 'BLE Address: ' + (data.address || 'Connected');
                if (interactive) showToast('Printer found: ' + data.printer_name, 'text-bg-success');
            } else {
                badgeEl.className = 'badge bg-danger-subtle text-danger-emphasis';
                badgeEl.innerHTML = '<i class="bi bi-x-circle-fill me-1 small"></i> Offline';
                nameEl.innerText = 'Printer Not Detected';
                addrEl.innerText = 'Make sure printer is powered on and in Bluetooth range';
                if (interactive) showToast('Printer is offline or out of range', 'text-bg-danger');
            }
        }
    } catch (e) {
        badgeEl.className = 'badge bg-danger-subtle text-danger-emphasis';
        badgeEl.innerText = 'Error';
        nameEl.innerText = 'Connection Error';
    } finally {
        if (icon) icon.classList.remove('bi-spin');
    }
}

async function testFeedPaper() {
    showToast('Sending paper feed command...');
    try {
        const res = await fetch('/api/internal/feed', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Paper fed successfully!', 'text-bg-success');
        } else {
            showToast(data.error || 'Failed to feed paper', 'text-bg-danger');
        }
    } catch (e) {
        showToast('Error sending feed command', 'text-bg-danger');
    }
}
