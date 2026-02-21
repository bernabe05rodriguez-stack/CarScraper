// Auth helper - manages username display + logout

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

    // Render user info + logout in navbar
    renderNavUser() {
        const nav = document.querySelector('.navbar');
        if (!nav || nav.querySelector('.navbar-user')) return;

        const userEl = document.createElement('div');
        userEl.className = 'navbar-user';
        userEl.innerHTML = `
            <span class="navbar-username">${this.getUsername()}</span>
            <button class="btn-logout" onclick="Auth.logout()">Logout</button>
        `;
        nav.appendChild(userEl);
    },
};

// Render nav user on protected pages
if (!window.location.pathname.startsWith('/login')) {
    document.addEventListener('DOMContentLoaded', () => Auth.renderNavUser());
}
