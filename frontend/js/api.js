// API wrapper

const API = {
    BASE: '/api/v1',

    async get(path) {
        const resp = await fetch(this.BASE + path);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return resp.json();
    },

    async post(path, data) {
        const resp = await fetch(this.BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return resp.json();
    },

    async getMakes() {
        return this.get('/makes');
    },

    async getModels(make) {
        return this.get('/models/' + encodeURIComponent(make));
    },

    async searchAuctions(params) {
        return this.post('/auctions/search', params);
    },

    async getJobStatus(jobId) {
        return this.get('/jobs/' + jobId);
    },

    async getAuctionResults(jobId) {
        return this.get('/auctions/results/' + jobId);
    },

    getExportUrl(jobId) {
        return this.BASE + '/export/' + jobId;
    },
};
