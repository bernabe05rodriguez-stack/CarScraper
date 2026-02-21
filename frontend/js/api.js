// API wrapper

const API = {
    BASE: '/api/v1',

    _headers() {
        const h = { 'Content-Type': 'application/json' };
        const token = localStorage.getItem('auth_token');
        if (token) h['Authorization'] = 'Bearer ' + token;
        return h;
    },

    _handleUnauth(resp) {
        if (resp.status === 401) {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_username');
            window.location.href = '/login';
            throw new Error('Session expired');
        }
    },

    async get(path) {
        const resp = await fetch(this.BASE + path, { headers: this._headers() });
        this._handleUnauth(resp);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return resp.json();
    },

    async post(path, data) {
        const resp = await fetch(this.BASE + path, {
            method: 'POST',
            headers: this._headers(),
            body: JSON.stringify(data),
        });
        this._handleUnauth(resp);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return resp.json();
    },

    // Makes/Models
    async getMakes() {
        return this.get('/makes');
    },

    async getModels(make) {
        return this.get('/models/' + encodeURIComponent(make));
    },

    // Auctions
    async searchAuctions(params) {
        return this.post('/auctions/search', params);
    },

    async getAuctionResults(jobId) {
        return this.get('/auctions/results/' + jobId);
    },

    // Used Cars
    async searchUsedCars(params) {
        return this.post('/used-cars/search', params);
    },

    async getUsedCarResults(jobId) {
        return this.get('/used-cars/results/' + jobId);
    },

    // Comparison
    async analyzeComparison(params) {
        return this.post('/comparison/analyze', params);
    },

    // Jobs
    async getJobStatus(jobId) {
        return this.get('/jobs/' + jobId);
    },

    // Export
    getExportUrl(jobId) {
        const token = localStorage.getItem('auth_token');
        return this.BASE + '/export/' + jobId + (token ? '?token=' + token : '');
    },
};
