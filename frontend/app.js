/* ═══════════════════════════════════════════════════════════
   El Descargador Pro — Application Logic
   ═══════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── Configuration ───────────────────────────────────────
    // TODO: Replace with your actual Render backend URL
    const API_BASE = window.location.origin;

    // ── DOM Elements ────────────────────────────────────────
    const $  = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const urlInput       = $('#url-input');
    const pasteBtn       = $('#paste-btn');
    const searchBtn      = $('#search-btn');
    const errorMessage   = $('#error-message');
    const errorText      = $('#error-text');

    const previewSection = $('#preview-section');
    const previewThumb   = $('#preview-thumb');
    const previewDuration = $('#preview-duration');
    const previewTitle   = $('#preview-title');
    const previewSource  = $('#preview-source');

    const formatToggle   = $('#format-toggle');
    const qualityGrid    = $('#quality-grid');
    const downloadBtn    = $('#download-btn');

    const progressSection = $('#progress-section');
    const progressBar    = $('#progress-bar');
    const progressStatus = $('#progress-status');
    const progressPercent = $('#progress-percent');
    const progressSpeed  = $('#progress-speed');
    const progressEta    = $('#progress-eta');

    const completeSection = $('#complete-section');
    const completeFilename = $('#complete-filename');
    const newDownloadBtn = $('#new-download-btn');

    const navbar = $('#navbar');

    // ── State ───────────────────────────────────────────────
    let currentFormat  = 'mp4';
    let currentQuality = 1080;
    let currentMetadata = null;
    let pollInterval   = null;

    const VIDEO_QUALITIES = [
        { value: 1080, label: '1080p' },
        { value: 720,  label: '720p' },
        { value: 480,  label: '480p' },
        { value: 360,  label: '360p' },
    ];

    const AUDIO_QUALITIES = [
        { value: 320, label: '320 kbps' },
        { value: 256, label: '256 kbps' },
        { value: 192, label: '192 kbps' },
        { value: 128, label: '128 kbps' },
    ];

    // ── Initialization ──────────────────────────────────────
    function init() {
        setupEventListeners();
        renderQualities();
    }

    function setupEventListeners() {
        // URL input validation
        urlInput.addEventListener('input', onUrlChange);
        urlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !searchBtn.disabled) {
                searchBtn.click();
            }
        });

        // Paste button
        pasteBtn.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                urlInput.value = text;
                onUrlChange();
                urlInput.focus();
            } catch {
                // Clipboard API might fail — silently ignore
                urlInput.focus();
            }
        });

        // Search
        searchBtn.addEventListener('click', onSearch);

        // Format toggle
        $$('.format-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const fmt = btn.dataset.format;
                if (fmt === currentFormat) return;
                currentFormat = fmt;
                
                // Update toggle UI
                $$('.format-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                formatToggle.dataset.active = fmt;
                
                // Update quality options
                renderQualities();
            });
        });

        // Download
        downloadBtn.addEventListener('click', onDownload);

        // New download
        newDownloadBtn.addEventListener('click', resetAll);

        // Navbar scroll effect
        window.addEventListener('scroll', () => {
            navbar.classList.toggle('scrolled', window.scrollY > 20);
        });
    }

    // ── URL Validation ──────────────────────────────────────
    function isValidUrl(str) {
        try {
            const url = new URL(str);
            return ['http:', 'https:'].includes(url.protocol);
        } catch {
            return false;
        }
    }

    function onUrlChange() {
        const valid = isValidUrl(urlInput.value.trim());
        searchBtn.disabled = !valid;
        hideError();
    }

    // ── Search (Metadata Extraction) ────────────────────────
    async function onSearch() {
        const url = urlInput.value.trim();
        if (!isValidUrl(url)) return;

        setSearchLoading(true);
        hideError();
        hidePreview();
        hideProgress();
        hideComplete();

        try {
            const res = await fetch(`${API_BASE}/api/metadata`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || `Error del servidor (${res.status})`);
            }

            const data = await res.json();
            currentMetadata = data;
            showPreview(data);
        } catch (err) {
            showError(err.message || 'No se pudo conectar con el servidor.');
        } finally {
            setSearchLoading(false);
        }
    }

    function setSearchLoading(loading) {
        const btnText  = searchBtn.querySelector('.btn-text');
        const btnIcon  = searchBtn.querySelector('.btn-icon');
        const btnLoader = searchBtn.querySelector('.btn-loader');

        if (loading) {
            searchBtn.disabled = true;
            urlInput.disabled = true;
            btnText.textContent = 'Buscando...';
            btnIcon.style.display = 'none';
            btnLoader.style.display = 'flex';
        } else {
            searchBtn.disabled = !isValidUrl(urlInput.value.trim());
            urlInput.disabled = false;
            btnText.textContent = 'Buscar';
            btnIcon.style.display = 'block';
            btnLoader.style.display = 'none';
        }
    }

    // ── Preview Display ─────────────────────────────────────
    function showPreview(data) {
        previewTitle.textContent = data.title || 'Sin título';
        previewSource.textContent = data.extractor || 'Desconocido';
        previewThumb.src = data.thumbnail_url || '';
        previewThumb.alt = data.title || 'Thumbnail';
        
        if (data.duration_seconds) {
            const m = Math.floor(data.duration_seconds / 60);
            const s = Math.floor(data.duration_seconds % 60);
            previewDuration.textContent = `${m}:${s.toString().padStart(2, '0')}`;
        } else {
            previewDuration.textContent = '';
        }

        previewSection.style.display = 'block';
    }

    function hidePreview() {
        previewSection.style.display = 'none';
    }

    // ── Quality Rendering ───────────────────────────────────
    function renderQualities() {
        const opts = currentFormat === 'mp4' ? VIDEO_QUALITIES : AUDIO_QUALITIES;
        qualityGrid.innerHTML = '';

        opts.forEach((q, i) => {
            const btn = document.createElement('button');
            btn.className = 'quality-option' + (i === 0 ? ' active' : '');
            btn.textContent = q.label;
            btn.dataset.value = q.value;
            btn.addEventListener('click', () => {
                $$('.quality-option').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentQuality = q.value;
            });
            qualityGrid.appendChild(btn);
        });

        currentQuality = opts[0].value;
    }

    // ── Download ────────────────────────────────────────────
    async function onDownload() {
        if (!currentMetadata) return;
        
        const url = urlInput.value.trim();

        downloadBtn.disabled = true;
        previewSection.style.display = 'none';
        showProgress();

        try {
            const res = await fetch(`${API_BASE}/api/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url,
                    format: currentFormat,
                    quality: currentQuality,
                }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || `Error del servidor (${res.status})`);
            }

            const data = await res.json();
            
            if (data.download_id) {
                startProgressPolling(data.download_id);
            }
        } catch (err) {
            hideProgress();
            showError(err.message || 'Error al iniciar la descarga.');
            downloadBtn.disabled = false;
            previewSection.style.display = 'block';
        }
    }

    // ── Progress Polling ────────────────────────────────────
    function startProgressPolling(downloadId) {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE}/api/progress/${downloadId}`);
                if (!res.ok) return;

                const data = await res.json();

                updateProgress(data);

                if (data.state === 'complete') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    
                    // Trigger the file download in the browser
                    triggerFileDownload(downloadId);
                } else if (data.state === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    hideProgress();
                    showError(data.error || 'La descarga falló.');
                    downloadBtn.disabled = false;
                }
            } catch {
                // Silently retry on network errors during polling
            }
        }, 800);
    }

    function updateProgress(data) {
        const pct = Math.round(data.percent || 0);
        progressBar.style.width = pct + '%';
        progressPercent.textContent = pct + '%';
        progressStatus.textContent = data.status_text || 'Descargando...';
        progressSpeed.textContent = data.speed || '—';
        progressEta.textContent = data.eta ? `ETA: ${data.eta}` : '—';
    }

    function triggerFileDownload(downloadId) {
        const link = document.createElement('a');
        link.href = `${API_BASE}/api/file/${downloadId}`;
        link.download = '';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // Show complete state
        hideProgress();
        showComplete(currentMetadata?.title || 'archivo');
    }

    // ── UI State Helpers ────────────────────────────────────
    function showError(msg) {
        errorText.textContent = msg;
        errorMessage.style.display = 'flex';
    }

    function hideError() {
        errorMessage.style.display = 'none';
    }

    function showProgress() {
        progressSection.style.display = 'block';
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';
        progressStatus.textContent = 'Preparando descarga...';
        progressSpeed.textContent = '—';
        progressEta.textContent = '—';
    }

    function hideProgress() {
        progressSection.style.display = 'none';
    }

    function showComplete(filename) {
        completeFilename.textContent = filename;
        completeSection.style.display = 'block';
    }

    function hideComplete() {
        completeSection.style.display = 'none';
    }

    function resetAll() {
        urlInput.value = '';
        urlInput.disabled = false;
        searchBtn.disabled = true;
        downloadBtn.disabled = false;
        currentMetadata = null;
        currentFormat = 'mp4';

        // Reset format toggle
        $$('.format-btn').forEach(b => b.classList.remove('active'));
        $('#format-mp4').classList.add('active');
        formatToggle.dataset.active = 'mp4';
        renderQualities();

        hideError();
        hidePreview();
        hideProgress();
        hideComplete();

        urlInput.focus();
    }

    // ── Initialize ──────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', init);
})();
