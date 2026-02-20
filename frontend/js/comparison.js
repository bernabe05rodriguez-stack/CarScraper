// Comparison page logic

(function () {
    const makeSelect = document.getElementById('make');
    const modelSelect = document.getElementById('model');
    const yearFromSelect = document.getElementById('year-from');
    const yearToSelect = document.getElementById('year-to');
    const compareForm = document.getElementById('compare-form');
    const compareBtn = document.getElementById('compare-btn');
    const resultsSection = document.getElementById('results-section');
    const usaStats = document.getElementById('usa-stats');
    const germanyStats = document.getElementById('germany-stats');
    const arbitrageSummary = document.getElementById('arbitrage-summary');

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

    compareForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const make = makeSelect.value;
        if (!make) { alert('Please select a make'); return; }

        const params = {
            make: make,
            model: modelSelect.value || null,
            year_from: yearFromSelect.value ? parseInt(yearFromSelect.value) : null,
            year_to: yearToSelect.value ? parseInt(yearToSelect.value) : null,
        };

        compareBtn.disabled = true;
        compareBtn.textContent = 'Analyzing...';

        try {
            const data = await API.analyzeComparison(params);
            renderResults(data);
            resultsSection.classList.add('active');
        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            compareBtn.disabled = false;
            compareBtn.textContent = 'Compare';
        }
    });

    function renderResults(data) {
        const s = data.stats;

        // USA panel
        if (s.usa) {
            usaStats.innerHTML = `
                <div class="comparison-stat-list">
                    <div class="comparison-stat"><span>Listings:</span> <strong>${s.usa.count}</strong></div>
                    ${s.usa.mean_price != null ? `<div class="comparison-stat"><span>Mean Price:</span> <strong>${formatCurrency(s.usa.mean_price)}</strong></div>` : ''}
                    ${s.usa.median_price != null ? `<div class="comparison-stat"><span>Median Price:</span> <strong>${formatCurrency(s.usa.median_price)}</strong></div>` : ''}
                    ${s.usa.min_price != null ? `<div class="comparison-stat"><span>Min Price:</span> <strong>${formatCurrency(s.usa.min_price)}</strong></div>` : ''}
                    ${s.usa.max_price != null ? `<div class="comparison-stat"><span>Max Price:</span> <strong>${formatCurrency(s.usa.max_price)}</strong></div>` : ''}
                    ${s.usa.mean_days_on_market != null ? `<div class="comparison-stat"><span>Mean Days on Market:</span> <strong>${s.usa.mean_days_on_market}</strong></div>` : ''}
                </div>
                ${s.usa.count === 0 ? '<p style="color: var(--warning); margin-top: 0.5rem;">No USA data available. Run USA Used Cars searches first to populate data.</p>' : ''}
            `;
        }

        // Germany panel
        if (s.germany) {
            germanyStats.innerHTML = `
                <div class="comparison-stat-list">
                    <div class="comparison-stat"><span>Listings:</span> <strong>${s.germany.count}</strong></div>
                    ${s.germany.mean_price_eur != null ? `<div class="comparison-stat"><span>Mean Price:</span> <strong>${formatCurrency(s.germany.mean_price_eur, 'EUR')}</strong></div>` : ''}
                    ${s.germany.mean_price_usd != null ? `<div class="comparison-stat"><span>Mean Price (USD):</span> <strong>${formatCurrency(s.germany.mean_price_usd)}</strong></div>` : ''}
                    ${s.germany.median_price_eur != null ? `<div class="comparison-stat"><span>Median Price:</span> <strong>${formatCurrency(s.germany.median_price_eur, 'EUR')}</strong></div>` : ''}
                    ${s.germany.min_price_eur != null ? `<div class="comparison-stat"><span>Min Price:</span> <strong>${formatCurrency(s.germany.min_price_eur, 'EUR')}</strong></div>` : ''}
                    ${s.germany.max_price_eur != null ? `<div class="comparison-stat"><span>Max Price:</span> <strong>${formatCurrency(s.germany.max_price_eur, 'EUR')}</strong></div>` : ''}
                    ${s.germany.mean_days_on_market != null ? `<div class="comparison-stat"><span>Mean Days on Market:</span> <strong>${s.germany.mean_days_on_market}</strong></div>` : ''}
                </div>
                ${s.germany.count === 0 ? '<p style="color: var(--warning); margin-top: 0.5rem;">No Germany data available. Run Germany Used Cars searches first to populate data.</p>' : ''}
            `;
        }

        // Arbitrage
        if (s.price_delta_usd != null) {
            const isOpportunity = Math.abs(s.price_delta_pct) > 5;
            const deltaColor = s.price_delta_usd > 0 ? 'var(--success)' : 'var(--accent)';
            const sign = s.price_delta_usd > 0 ? '+' : '';

            arbitrageSummary.innerHTML = `
                <div class="arbitrage-result">
                    <div class="arbitrage-delta" style="color: ${deltaColor};">
                        ${sign}${formatCurrency(s.price_delta_usd)} (${sign}${s.price_delta_pct}%)
                    </div>
                    <div class="arbitrage-direction">
                        <strong>${s.arbitrage_direction}</strong>
                        ${isOpportunity ? ' - Potential Arbitrage Opportunity' : ' - Minimal difference'}
                    </div>
                    <div class="arbitrage-detail" style="margin-top: 0.5rem; color: var(--text-light);">
                        Exchange rate: 1 EUR = ${s.eur_usd_rate} USD
                    </div>
                </div>
            `;
        } else {
            arbitrageSummary.innerHTML = '<p style="color: var(--text-light);">Not enough data from both markets to calculate arbitrage. Search for listings in both USA and Germany first.</p>';
        }
    }
})();
