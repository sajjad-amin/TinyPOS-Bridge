function showToast(msg, bgClass = 'text-bg-primary') {
    const toastEl = document.getElementById('liveToast');
    const toastMsg = document.getElementById('toast-msg');
    if (!toastEl || !toastMsg) return;
    toastEl.className = `toast align-items-center ${bgClass} border-0`;
    toastMsg.innerText = msg;
    const toast = new bootstrap.Toast(toastEl);
    toast.show();
}
