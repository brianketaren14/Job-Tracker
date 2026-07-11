/* ── dashboard.js — Analytics charts + scrape panel ──────── */
'use strict';

// ── Plotly theme helpers ──────────────────────────────────
const COLORS = {
  accent:  '#4f8ef7',
  green:   '#22c55e',
  amber:   '#f59e0b',
  red:     '#ef4444',
  text1:   '#e8eaf0',
  text2:   '#8b92a8',
  text3:   '#4a5068',
  border:  '#1e2330',
  card:    '#111318',
  deep:    '#0a0c10',
};

const GRADIENT_BLUE = Array.from({ length: 20 }, (_, i) => {
  const t = i / 19;
  const r = Math.round(30  + t * (79  - 30));
  const g = Math.round(60  + t * (142 - 60));
  const b = Math.round(180 + t * (247 - 180));
  return `rgb(${r},${g},${b})`;
});

const plotLayout = (extra = {}) => ({
  paper_bgcolor: 'transparent',
  plot_bgcolor:  'transparent',
  font: { family: "'Inter', sans-serif", color: COLORS.text2, size: 11 },
  margin: { t: 10, r: 10, b: 40, l: 50 },
  xaxis: { gridcolor: COLORS.border, zerolinecolor: COLORS.border, tickfont: { color: COLORS.text3, size: 10 } },
  yaxis: { gridcolor: COLORS.border, zerolinecolor: COLORS.border, tickfont: { color: COLORS.text3, size: 10 } },
  ...extra,
});

const plotConfig = { displayModeBar: false, responsive: true };

// ── Load summary stats ────────────────────────────────────
async function loadSummary() {
  try {
    const [sumRes, statusRes] = await Promise.all([
      fetch('/api/analytics/summary'),
      fetch('/api/scrape/status'),
    ]);
    const sum    = await sumRes.json();
    const status = await statusRes.json();

    document.getElementById('stat-total-jobs').textContent   = sum.total_jobs.toLocaleString('id-ID');
    document.getElementById('stat-total-skills').textContent = sum.total_skills.toLocaleString('id-ID');
    document.getElementById('stat-latest').textContent       = sum.latest_posting || '—';
    document.getElementById('stat-last-run').textContent     = status.last_run || 'Belum pernah';

    renderStatusDot(status);
    renderHistory(status.history || []);
  } catch (e) { console.error('loadSummary:', e); }
}

// ── Chart: Top skills (horizontal bar) ───────────────────
async function loadSkillChart() {
  try {
    const res  = await fetch('/api/analytics/skills?limit=20');
    const data = await res.json();
    if (!data.labels?.length) return;

    const labels  = [...data.labels].reverse();
    const values  = [...data.values].reverse();
    const colors  = [...GRADIENT_BLUE].reverse();

    Plotly.newPlot('chart-skills', [{
      type: 'bar', orientation: 'h',
      x: values, y: labels,
      marker: { color: colors, opacity: .9 },
      hovertemplate: '<b>%{y}</b><br>%{x} lowongan<extra></extra>',
      text: values, textposition: 'outside',
      textfont: { color: COLORS.text2, size: 10 },
    }], plotLayout({
      margin: { t: 10, r: 60, b: 30, l: 140 },
      height: 400,
      xaxis: { gridcolor: COLORS.border, zerolinecolor: COLORS.border },
      yaxis: { gridcolor: 'transparent', zerolinecolor: 'transparent', tickfont: { color: COLORS.text1, size: 11 } },
    }), plotConfig);
  } catch (e) { console.error('loadSkillChart:', e); }
}

// ── Chart: Jobs per day (area line) ──────────────────────
async function loadTimelineChart() {
  try {
    const res  = await fetch('/api/analytics/jobs-per-day');
    const data = await res.json();
    if (!data.labels?.length) return;

    Plotly.newPlot('chart-timeline', [{
      type: 'scatter', mode: 'lines+markers',
      x: data.labels, y: data.values,
      fill: 'tozeroy',
      line: { color: COLORS.accent, width: 2.5 },
      marker: { color: COLORS.accent, size: 5 },
      fillcolor: 'rgba(79,142,247,0.08)',
      hovertemplate: '<b>%{x}</b><br>%{y} lowongan<extra></extra>',
    }], plotLayout({
      margin: { t: 10, r: 10, b: 50, l: 40 },
      xaxis: {
        type: 'date', gridcolor: COLORS.border,
        tickformat: '%d %b', tickangle: -30,
        tickfont: { color: COLORS.text3, size: 9 },
      },
      yaxis: { gridcolor: COLORS.border, tickfont: { color: COLORS.text3, size: 10 } },
    }), plotConfig);
  } catch (e) { console.error('loadTimelineChart:', e); }
}

// ── Chart: Schedule type (donut) ─────────────────────────
async function loadScheduleChart() {
  try {
    const res  = await fetch('/api/analytics/schedule-type');
    const data = await res.json();
    if (!data.labels?.length) return;

    const palette = [COLORS.accent, COLORS.green, COLORS.amber, COLORS.red, '#a78bfa', '#fb923c', '#38bdf8'];

    Plotly.newPlot('chart-schedule', [{
      type: 'pie',
      labels: data.labels,
      values: data.values,
      hole: .52,
      marker: { colors: palette, line: { color: COLORS.deep, width: 2 } },
      textinfo: 'percent',
      textfont: { color: '#fff', size: 11 },
      hovertemplate: '<b>%{label}</b><br>%{value} lowongan (%{percent})<extra></extra>',
    }], {
      paper_bgcolor: 'transparent',
      plot_bgcolor:  'transparent',
      font: { family: "'Inter', sans-serif", color: COLORS.text2, size: 11 },
      margin: { t: 10, r: 10, b: 10, l: 10 },
      legend: {
        orientation: 'v', x: 1.02, y: .5,
        font: { color: COLORS.text2, size: 10 },
        bgcolor: 'transparent',
      },
      showlegend: true,
    }, plotConfig);
  } catch (e) { console.error('loadScheduleChart:', e); }
}

// ── Scrape status dot ─────────────────────────────────────
function renderStatusDot(status) {
  const dot = document.getElementById('dot');
  dot.className = 'status-dot';
  if (status.running) dot.classList.add('running');
  else if (status.last_run_status === 'success') dot.classList.add('success');
  else if (status.last_run_status === 'error')   dot.classList.add('error');
}

// ── Render history table ──────────────────────────────────
function renderHistory(history) {
  const wrap = document.getElementById('history-wrap');
  const tbody = document.getElementById('history-body');
  if (!history.length) { wrap.style.display = 'none'; return; }

  wrap.style.display = 'block';
  tbody.innerHTML = history.map(h => `
    <tr>
      <td>${h.time}</td>
      <td><span class="badge-status ${h.status}">${h.status === 'success' ? '✓ Sukses' : '✗ Error'}</span></td>
      <td>${h.duration_sec != null ? h.duration_sec + 's' : '—'}</td>
      <td style="max-width:360px;color:var(--text-3)">${escHtml(h.message || '')}</td>
    </tr>`).join('');
}

// ── Manual scrape trigger ─────────────────────────────────
window.triggerScrape = async function () {
  const pw  = document.getElementById('pw-input').value;
  const btn = document.getElementById('scrape-btn');
  const alert = document.getElementById('scrape-alert');

  alert.className = 'alert';

  if (!pw) {
    showAlert(alert, 'error', 'Masukkan password terlebih dahulu.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Memulai…';

  try {
    const res  = await fetch('/api/scrape/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
    });
    const data = await res.json();

    if (res.ok) {
      showAlert(alert, 'success', data.message || 'Scraping dimulai di background.');
      document.getElementById('pw-input').value = '';
      pollStatus();
    } else {
      showAlert(alert, 'error', data.error || 'Terjadi kesalahan.');
    }
  } catch (e) {
    showAlert(alert, 'error', 'Gagal terhubung ke server.');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Jalankan Sekarang`;
  }
};

function showAlert(el, type, msg) {
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
  setTimeout(() => { el.className = 'alert'; }, 6000);
}

// ── Poll status while running ─────────────────────────────
let pollTimer = null;
async function pollStatus() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res    = await fetch('/api/scrape/status');
      const status = await res.json();
      renderStatusDot(status);
      renderHistory(status.history || []);
      document.getElementById('stat-last-run').textContent = status.last_run || 'Belum pernah';
      if (!status.running) clearInterval(pollTimer);
    } catch { clearInterval(pollTimer); }
  }, 3000);
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Init ─────────────────────────────────────────────────
loadSummary();
loadSkillChart();
loadTimelineChart();
loadScheduleChart();
