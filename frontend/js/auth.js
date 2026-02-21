// Auth + Theme helper

const Theme = {
    init() {
        const saved = localStorage.getItem('theme');
        if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    },
    toggle() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (isDark) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
        }
        // Update icon
        const btn = document.querySelector('.btn-theme');
        if (btn) btn.textContent = isDark ? '\u263C' : '\u263E';
    },
    getIcon() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? '\u263E' : '\u263C';
    }
};

// Apply theme immediately (before DOM renders)
Theme.init();

const Auth = {
    getToken() {
        return localStorage.getItem('auth_token');
    },

    getUsername() {
        return localStorage.getItem('auth_username') || '';
    },

    async logout() {
        try { await fetch('/api/v1/auth/logout', { method: 'POST' }); } catch (_) {}
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_username');
        window.location.href = '/login';
    },

    renderNavRight() {
        const nav = document.querySelector('.navbar');
        if (!nav || nav.querySelector('.navbar-right')) return;

        const el = document.createElement('div');
        el.className = 'navbar-right';
        el.innerHTML = `
            <button class="btn-theme" onclick="Theme.toggle()" title="Toggle theme">${Theme.getIcon()}</button>
            <span class="navbar-username">${this.getUsername()}</span>
            <button class="btn-logout" onclick="Auth.logout()">Logout</button>
        `;
        nav.appendChild(el);
    },
};

// Render nav on protected pages
if (!window.location.pathname.startsWith('/login')) {
    document.addEventListener('DOMContentLoaded', () => Auth.renderNavRight());
}
