let currentPage = 1;
let activeJobToDelete = null;

async function loadQueue(page = 1) {
    currentPage = page;
    const tbody = document.getElementById('queue-body');
    const badgeTotal = document.getElementById('queue-total-badge');
    const pagContainer = document.getElementById('queue-pagination-container');
    const pagInfo = document.getElementById('queue-pagination-info');
    const pagNav = document.getElementById('queue-pagination-nav');

    try {
        const res = await fetch(`/api/internal/queue?page=${page}&per_page=50`);
        const data = await res.json();
        const jobs = data.jobs || [];
        const total = data.total || 0;
        const totalPages = data.total_pages || 1;

        if (badgeTotal) badgeTotal.innerText = `${total} Total`;

        if (jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-5 text-muted"><i class="bi bi-inbox d-block fs-3 mb-2 opacity-50"></i>No print jobs in database yet.</td></tr>';
            if (pagContainer) pagContainer.style.setProperty('display', 'none', 'important');
            return;
        }

        let html = '';
        jobs.forEach(job => {
            let badge = '<span class="badge bg-secondary">Pending</span>';
            if (job.status === 'completed') badge = '<span class="badge bg-success-subtle text-success"><i class="bi bi-check-circle me-1"></i>Completed</span>';
            if (job.status === 'printing') badge = '<span class="badge bg-primary-subtle text-primary"><i class="bi bi-hourglass-split me-1"></i>Printing</span>';
            if (job.status === 'cancelled') badge = '<span class="badge bg-warning-subtle text-warning-emphasis"><i class="bi bi-stop-circle me-1"></i>Stopped</span>';
            if (job.status === 'failed') badge = `<span class="badge bg-danger-subtle text-danger" title="${job.error || 'Failed'}"><i class="bi bi-x-circle me-1"></i>Failed</span>`;

            const keepBadge = job.keep_job
                ? '<span class="badge bg-secondary-subtle text-secondary ms-1" title="Preserved permanently in SQLite"><i class="bi bi-bookmark-fill me-1"></i>Saved</span>'
                : '<span class="badge bg-warning-subtle text-warning-emphasis ms-1" title="Temporary - auto-purged after 5 minutes"><i class="bi bi-clock-history me-1"></i>Temp (5m)</span>';

            const srcBadge = job.api_key === 'test_page' 
                ? '<span class="badge bg-info-subtle text-info">Test Page</span>'
                : (job.api_key ? `<span class="badge bg-dark-subtle text-body font-monospace" title="${job.api_key}">API (${job.api_key.substring(0, 8)}...)</span>` : '<span class="badge bg-secondary-subtle text-secondary">Direct</span>');

            const createdTime = job.created_at ? job.created_at.substring(0, 19).replace('T', ' ') : '';

            const stopBtnHtml = (job.status === 'printing')
                ? `<button class="btn btn-sm btn-danger me-1" onclick="stopJob('${job.job_id}')" title="Stop Printing This Job"><i class="bi bi-stop-circle-fill"></i></button>`
                : '';

            html += `<tr>
                <td class="ps-3 font-monospace small"><span title="${job.job_id}">${job.job_id.substring(0, 8)}...</span></td>
                <td><span class="badge bg-body-secondary text-body text-uppercase">${job.job_type}</span></td>
                <td>${srcBadge}</td>
                <td>${badge} ${keepBadge}</td>
                <td class="small text-muted">
                    <span class="badge bg-light text-dark border">Str: ${job.strength || 7}</span>
                    <span class="badge bg-light text-dark border">Scale: ${Math.round((job.scale || 1.0) * 100)}%</span>
                </td>
                <td class="small text-muted">${createdTime}</td>
                <td class="text-end pe-3 text-nowrap">
                    ${stopBtnHtml}
                    <button class="btn btn-sm btn-outline-secondary me-1" onclick="openJobPreview('${job.job_id}')" title="Preview Raster">
                        <i class="bi bi-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="openDeleteJobModal('${job.job_id}')" title="Delete Job">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>`;
        });
        tbody.innerHTML = html;

        // Render Pagination
        if (pagContainer) {
            pagContainer.style.removeProperty('display');
            const startIdx = ((page - 1) * 50) + 1;
            const endIdx = Math.min(page * 50, total);
            pagInfo.innerText = `Showing jobs ${startIdx}-${endIdx} of ${total}`;

            if (totalPages > 1) {
                let navHtml = '';
                navHtml += `<li class="page-item ${page <= 1 ? 'disabled' : ''}">
                    <a class="page-link" href="javascript:void(0)" onclick="loadQueue(${page - 1})"><i class="bi bi-chevron-left"></i></a>
                </li>`;

                for (let p = 1; p <= totalPages; p++) {
                    if (p === page) {
                        navHtml += `<li class="page-item active"><span class="page-link">${p}</span></li>`;
                    } else if (p <= 3 || p >= totalPages - 2 || (p >= page - 1 && p <= page + 1)) {
                        navHtml += `<li class="page-item"><a class="page-link" href="javascript:void(0)" onclick="loadQueue(${p})">${p}</a></li>`;
                    } else if (p === 4 || p === totalPages - 3) {
                        navHtml += `<li class="page-item disabled"><span class="page-link">&hellip;</span></li>`;
                    }
                }

                navHtml += `<li class="page-item ${page >= totalPages ? 'disabled' : ''}">
                    <a class="page-link" href="javascript:void(0)" onclick="loadQueue(${page + 1})"><i class="bi bi-chevron-right"></i></a>
                </li>`;
                pagNav.innerHTML = navHtml;
            } else {
                pagNav.innerHTML = '';
            }
        }
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-3 text-danger">Failed to load print queue</td></tr>';
    }
}

function openJobPreview(jobId) {
    document.getElementById('preview-img').src = `/api/print/preview/${jobId}`;
    new bootstrap.Modal(document.getElementById('previewModal')).show();
}

function openDeleteJobModal(jobId) {
    activeJobToDelete = jobId;
    document.getElementById('delete-job-id-display').innerText = 'ID: ' + jobId;
    new bootstrap.Modal(document.getElementById('deleteJobModal')).show();
}

async function executeDeleteJob() {
    if (!activeJobToDelete) return;
    const btn = document.getElementById('confirm-delete-job-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Deleting...';

    try {
        const res = await fetch(`/api/internal/jobs/${activeJobToDelete}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('deleteJobModal')).hide();
            showToast('Job record deleted successfully', 'text-bg-success');
            loadQueue(currentPage);
        } else {
            showToast(data.message || 'Failed to delete job', 'text-bg-danger');
        }
    } catch (e) {
        showToast('Delete request error: ' + e.message, 'text-bg-danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-trash-fill me-1"></i> Delete';
    }
}

function openClearAllModal() {
    new bootstrap.Modal(document.getElementById('clearAllModal')).show();
}

async function executeClearAllJobs() {
    const btn = document.getElementById('confirm-clear-all-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Clearing...';

    try {
        const res = await fetch('/api/internal/jobs/clear', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('clearAllModal')).hide();
            showToast(`Cleared ${data.count} jobs from history!`, 'text-bg-success');
            loadQueue(1);
        } else {
            showToast(data.message || 'Failed to clear jobs', 'text-bg-danger');
        }
    } catch (e) {
        showToast('Clear request error: ' + e.message, 'text-bg-danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-trash-fill me-1"></i> Yes, Clear All';
    }
}
