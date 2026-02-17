// Utility functions

function formatCurrency(value) {
    if (value == null) return '-';
    return '$' + Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function formatNumber(value) {
    if (value == null) return '-';
    return Number(value).toLocaleString('en-US');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
