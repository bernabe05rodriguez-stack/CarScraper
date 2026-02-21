// Auth helper - manages token in localStorage

const Auth = {
    getToken() {
        return localStorage.getItem('auth_token');
    },

    getUsername() {
        return localStorage.getItem('auth_username') || '';
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_username');
        window.location.href = '/login';
    },

    // Call on every protected page load
    check() {
        if (!this.isLoggedIn()) {
            window.location.href = '/login';
            return false;
        }
        this.renderNavUser();
        return true;
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

// Auto-check auth on page load (except login page)
if (!window.location.pathname.startsWith('/login')) {
    document.addEventListener('DOMContentLoaded', () => Auth.check());
}
