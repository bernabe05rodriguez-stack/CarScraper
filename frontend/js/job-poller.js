// Job polling module

class JobPoller {
    constructor(jobId, { onProgress, onComplete, onError, interval = 2000 }) {
        this.jobId = jobId;
        this.onProgress = onProgress;
        this.onComplete = onComplete;
        this.onError = onError;
        this.interval = interval;
        this._timer = null;
        this._stopped = false;
    }

    start() {
        this._stopped = false;
        this._poll();
    }

    stop() {
        this._stopped = true;
        if (this._timer) {
            clearTimeout(this._timer);
            this._timer = null;
        }
    }

    async _poll() {
        if (this._stopped) return;

        try {
            const status = await API.getJobStatus(this.jobId);

            if (this.onProgress) {
                this.onProgress(status);
            }

            if (status.status === 'completed') {
                this.stop();
                if (this.onComplete) {
                    this.onComplete(status);
                }
                return;
            }

            if (status.status === 'failed') {
                this.stop();
                if (this.onError) {
                    this.onError(status.error_message || 'Search failed');
                }
                return;
            }

            // Schedule next poll
            this._timer = setTimeout(() => this._poll(), this.interval);

        } catch (err) {
            if (!this._stopped) {
                this._timer = setTimeout(() => this._poll(), this.interval);
            }
        }
    }
}
