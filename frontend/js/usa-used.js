// USA Used Cars page logic

(function () {
    const makeSelect = document.getElementById('make');
    const modelSelect = document.getElementById('model');
    const yearFromSelect = document.getElementById('year-from');
    const yearToSelect = document.getElementById('year-to');
    const searchForm = document.getElementById('search-form');
    const searchBtn = document.getElementById('search-btn');
    const clearBtn = document.getElementById('clear-btn');
    const progressSection = document.getElementById('progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultsSection = document.getElementById('results-section');
    const statsBar = document.getElementById('stats-bar');
    const resultsBody = document.getElementById('results-body');
    const noResults = document.getElementById('no-results');
    const exportBtn = document.getElementById('export-btn');

    let currentJobId = null;
    let currentPoller = null;
    let allListings = [];
    let sortField = null;
    let sortAsc = true;

    loadMakes();
    populateYears();

    async function loadMakes() {
        try {
            const makes = await API.getMakes();
            makes.forEach(make => {
                const opt = document.createElement('option');
                opt.value = make;
                opt.textContent = make;
                makeSelect.appendChild(opt);
            });
        } catch (err) {
            console.error('Failed to load makes:', err);
        }
    }

    makeSelect.addEventListener('change', async () => {
        modelSelect.innerHTML = '<option value="">All Models</option>';
        const make = makeSelect.value;
        if (!make) return;
        try {
            const models = await API.getModels(make);
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modelSelect.appendChild(opt);
            });
        } catch (err) {
            console.error('Failed to load models:', err);
        }
    });

    function populateYears() {
        const currentYear = new Date().getFullYear() + 1;
        for (let y = currentYear; y >= 1950; y--) {
            yearFromSelect.appendChild(new Option(y, y));
            yearToSelect.appendChild(new Option(y, y));
        }
    }

    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const make = makeSelect.value;
        if (!make) { alert('Please select a make'); return; }

        const platforms = [];
        document.querySelectorAll('input[name="platform"]:checked').forEach(cb => platforms.push(cb.value));
        if (platforms.length === 0) { alert('Please select at least one platform'); return; }

        const params = {
            make: make,
            model: modelSelect.value || null,
            year_from: yearFromSelect.value ? parseInt(yearFromSelect.value) : null,
            year_to: yearToSelect.value ? parseInt(yearToSelect.value) : null,
            keyword: document.getElementById('keyword').value || null,
            platforms: platforms,
            region: 'usa',
        };

        await startSearch(params);
    });

    async function startSearch(params) {
        searchBtn.disabled = true;
        searchBtn.textContent = 'Searching...';
        progressSection.classList.add('active');
        resultsSection.classList.remove('active');
        progressBar.style.width = '0%';
        progressText.textContent = 'Starting search...';

        try {
            const response = await API.searchUsedCars(params);
            currentJobId = response.job_id;

            if (response.cached) {
                progressBar.style.width = '100%';
                progressText.textContent = 'Loaded from cache';
                await loadResults(currentJobId);
                return;
            }

            currentPoller = new JobPoller(currentJobId, {
                onProgress: (status) => {
                    progressBar.style.width = status.progress + '%';
                    progressText.textContent = `Searching... ${status.progress}% (${status.total_results} results so far)`;
                },
                onComplete: async (status) => {
                    progressBar.style.width = '100%';
                    progressText.textContent = `Done! ${status.total_results} results found.`;
                    await loadResults(currentJobId);
                },
                onError: (msg) => {
                    progressText.textContent = 'Error: ' + msg;
                    searchBtn.disabled = false;
                    searchBtn.textContent = 'Search';
                },
            });
            currentPoller.start();
        } catch (err) {
            progressText.textContent = 'Error: ' + err.message;
            searchBtn.disabled = false;
            searchBtn.textContent = 'Search';
        }
    }

    async function loadResults(jobId) {
        try {
            const data = await API.getUsedCarResults(jobId);
            allListings = data.listings;
            renderStats(data.stats);
            renderTable(allListings);
            resultsSection.classList.add('active');

            if (allListings.length > 0) {
                exportBtn.style.display = 'inline-flex';
                exportBtn.onclick = () => window.open(API.getExportUrl(jobId), '_blank');
            }
        } catch (err) {
            console.error('Failed to load results:', err);
        } finally {
            searchBtn.disabled = false;
            searchBtn.textContent = 'Search';
        }
    }

    function renderStats(stats) {
        if (!stats) { statsBar.innerHTML = ''; return; }
        let html = '';
        if (stats.total_listings != null) {
            html += `<div class="stat-item"><strong>${stats.total_listings}</strong> Total Listings</div>`;
        }
        if (stats.mean_list_price != null) {
            html += `<div class="stat-item">Mean Price: <strong>${formatCurrency(stats.mean_list_price)}</strong></div>`;
        }
        if (stats.median_list_price != null) {
            html += `<div class="stat-item">Median Price: <strong>${formatCurrency(stats.median_list_price)}</strong></div>`;
        }
        if (stats.min_list_price != null && stats.max_list_price != null) {
            html += `<div class="stat-item">Range: <strong>${formatCurrency(stats.min_list_price)}</strong> - <strong>${formatCurrency(stats.max_list_price)}</strong></div>`;
        }
        if (stats.mean_days_on_market != null) {
            html += `<div class="stat-item">Mean Days on Market: <strong>${stats.mean_days_on_market}</strong></div>`;
        }
        if (stats.mean_mileage != null) {
            html += `<div class="stat-item">Mean Mileage: <strong>${formatNumber(stats.mean_mileage)}</strong></div>`;
        }
        statsBar.innerHTML = html;
    }

    function renderTable(listings) {
        if (listings.length === 0) {
            resultsBody.innerHTML = '';
            noResults.style.display = 'block';
            return;
        }
        noResults.style.display = 'none';

        resultsBody.innerHTML = listings.map(l => `
            <tr>
                <td>${l.year || '-'}</td>
                <td>${escapeHtml(l.make) || '-'}</td>
                <td>${escapeHtml(l.model) || '-'}</td>
                <td>${escapeHtml(l.trim) || '-'}</td>
                <td>${formatCurrency(l.list_price, l.currency)}</td>
                <td>${l.mileage != null ? formatNumber(l.mileage) : '-'}</td>
                <td>${l.days_on_market != null ? l.days_on_market : '-'}</td>
                <td>${escapeHtml(l.dealer_name) || '-'}</td>
                <td>${escapeHtml(l.platform)}</td>
                <td>${l.url ? `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">View</a>` : '-'}</td>
            </tr>
        `).join('');
    }

    // Column sorting
    document.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            if (sortField === field) { sortAsc = !sortAsc; }
            else { sortField = field; sortAsc = true; }

            document.querySelectorAll('th[data-sort]').forEach(h => h.classList.remove('sorted'));
            th.classList.add('sorted');
            th.querySelector('.sort-arrow').textContent = sortAsc ? '\u25B2' : '\u25BC';

            const sorted = [...allListings].sort((a, b) => {
                let va = a[field], vb = b[field];
                if (va == null) va = sortAsc ? Infinity : -Infinity;
                if (vb == null) vb = sortAsc ? Infinity : -Infinity;
                if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
                return sortAsc ? va - vb : vb - va;
            });
            renderTable(sorted);
        });
    });

    clearBtn.addEventListener('click', () => {
        searchForm.reset();
        modelSelect.innerHTML = '<option value="">All Models</option>';
        progressSection.classList.remove('active');
        resultsSection.classList.remove('active');
        if (currentPoller) currentPoller.stop();
    });
})();
