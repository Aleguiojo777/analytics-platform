/* ══════════════════════════════════════
   DataLens — Frontend Application Logic
   ══════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────────
let connInfo = null;          // DB connection details
let availableTables = [];
let selectedTable = null;
let analyticsData = null;
let charts = {};              // Chart.js instances

// ── Init ───────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  showApp();
});

function showApp() {
  document.getElementById('appScreen').classList.remove('d-none');
  document.getElementById('appScreen').style.display = 'flex';
  populateUserInfo();
}

function populateUserInfo() {
  const initial = 'A';
  document.getElementById('userAvatar').textContent = initial;
  document.getElementById('sidebarUserName').textContent = 'Administrator';
  document.getElementById('sidebarUserRole').textContent = 'Analyst';
}

// ── Navigation ─────────────────────────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const panelMap = { connect: 'panelConnect', dashboard: 'panelDashboard', insights: 'panelInsights', data: 'panelData' };
  const titleMap = { connect: 'Connect to Database', dashboard: 'Analytics Dashboard', insights: 'AI Insights', data: 'Data Preview' };

  const panel = document.getElementById(panelMap[name]);
  if (panel) panel.classList.add('active');

  document.getElementById('topbarTitle').textContent = titleMap[name] || '';

  // Highlight matching nav item
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    if (item.getAttribute('onclick')?.includes(`'${name}'`)) item.classList.add('active');
  });

  // On mobile, collapse sidebar after navigation
  if (window.innerWidth <= 768) {
    document.getElementById('sidebar').classList.remove('mobile-open');
  }

  // Load AI insights when panel is opened
  if (name === 'insights' && selectedTable) {
    loadAIInsights(selectedTable);
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const main = document.querySelector('.main-content');
  if (window.innerWidth <= 768) {
    sidebar.classList.toggle('mobile-open');
  } else {
    sidebar.classList.toggle('collapsed');
    main.classList.toggle('expanded');
  }
}

// ── DB Connect ─────────────────────────────────────────────────────────
async function doConnect() {
  const server   = document.getElementById('dbServer').value.trim();
  const port     = document.getElementById('dbPort').value.trim();
  const database = document.getElementById('dbName').value.trim();
  const username = document.getElementById('dbUser').value.trim();
  const password = document.getElementById('dbPass').value;
  const encrypt  = document.getElementById('dbEncrypt').checked;
  const trustCert= document.getElementById('dbTrustCert').checked;
  const errEl    = document.getElementById('connectError');
  const sucEl    = document.getElementById('connectSuccess');

  hideEl(errEl); hideEl(sucEl);
  if (!server || !database || !username || !password) return showError(errEl, 'Server, database, username, and password are required.');
  if (!/^[A-Za-z0-9_.\\,\-:]+$/.test(server)) return showError(errEl, 'Server contains invalid characters.');
  if (port && (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535)) return showError(errEl, 'Port must be between 1 and 65535.');
  if ([server, database, username, password].some(hasControlChars)) return showError(errEl, 'Fields contain invalid characters.');

  const btn = document.getElementById('btnConnect');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;margin:0 auto"></div>';

  connInfo = { server, port, database, username, password, encrypt, trustCert };

  try {
    const res = await post('/api/db/connect', connInfo);
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';

    if (res.error) return showError(errEl, res.error);

    availableTables = res.tables;
    const filtered = Number(res.filteredTableCount || 0);
    const filteredText = filtered ? ` (${filtered} hidden because they are not analytics-ready)` : '';
    showSuccess(sucEl, `Connected to "${res.database}" - ${res.tableCount} analytics-ready table(s) available${filteredText}`);

    // Show DB badge in topbar
    const badge = document.getElementById('dbBadge');
    badge.classList.remove('d-none');
    document.getElementById('dbBadgeText').textContent = `${res.database} (${res.tableCount} ready tables)`;

    renderTableList(res.tables);
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';
    showError(errEl, 'Network error. Is the server running?');
  }
}

function hasControlChars(value) {
  return /[\x00-\x1F\x7F]/.test(String(value));
}

function renderTableList(tables) {
  const card = document.getElementById('tableListCard');
  const list = document.getElementById('tableList');
  const badge = document.getElementById('tableCountBadge');
  const search = document.getElementById('tableSearch')?.value.trim().toLowerCase() || '';
  const filteredTables = tables.filter(t => tableLabel(t).toLowerCase().includes(search));

  badge.textContent = filteredTables.length;
  list.innerHTML = '';

  if (filteredTables.length === 0) {
    list.innerHTML = '<p style="color:var(--text-muted);font-size:12px;padding:8px">No matching tables found.</p>';
  } else {
    filteredTables.forEach(t => {
      const item = document.createElement('div');
      const profile = t.profile || {};
      const details = [
        profile.rowCount !== undefined ? `${fmt(profile.rowCount)} rows` : null,
        profile.suggestedView ? profile.suggestedView.replace('-', ' ') : null
      ].filter(Boolean).join(' / ');
      item.className = tableLabel(t) === tableLabel(selectedTable) ? 'table-item selected' : 'table-item';
      item.innerHTML = `
        <i class="bi bi-table"></i>
        <span class="table-item-main">
          <span>${escHtml(tableLabel(t))}</span>
          ${details ? `<small>${escHtml(details)}</small>` : ''}
        </span>
      `;
      item.addEventListener('click', () => selectTable(t, item));
      list.appendChild(item);
    });
  }

  card.style.display = 'block';
}

function filterTableList() {
  renderTableList(availableTables);
}

async function refreshSelectedTable() {
  if (!selectedTable) return;
  await loadAnalytics(selectedTable);
}

async function selectTable(tableName, itemEl) {
  document.querySelectorAll('.table-item').forEach(i => i.classList.remove('selected'));
  itemEl.classList.add('selected');
  selectedTable = tableName;

  // Navigate to dashboard and load analytics
  showPanel('dashboard');
  await loadAnalytics(tableName);
}

// ── Analytics ──────────────────────────────────────────────────────────
async function loadAnalytics(tableName) {
  const loading = document.getElementById('dashLoading');
  const content = document.getElementById('dashContent');
  const empty   = document.getElementById('dashEmpty');

  resetAIInsightCards();
  content.classList.add('d-none');
  empty.classList.add('d-none');
  loading.classList.remove('d-none');
  document.getElementById('dashTableName').textContent = `Table: ${tableLabel(tableName)}`;

  try {
    const res = await post('/api/analytics/table', { connInfo, tableName: tablePayload(tableName) });
    loading.classList.add('d-none');

    if (res.error) {
      empty.classList.remove('d-none');
      empty.querySelector('p').textContent = res.error;
      return;
    }

    analyticsData = res;
    renderDashboard(res);
    renderDataTable(res.sampleRows, res.columns);
    content.classList.remove('d-none');
  } catch (e) {
    loading.classList.add('d-none');
    empty.classList.remove('d-none');
    empty.querySelector('p').textContent = 'Failed to load analytics.';
  }
}

function renderDashboard(data) {
  renderStats(data);
  renderCharts(data);
}

function renderStats(data) {
  const row = document.getElementById('statsRow');
  row.innerHTML = '';

  const profile = data.profile || {};
  const accentList = ['var(--accent)', 'var(--accent2)', 'var(--accent3)', 'var(--accent4)'];
  const suggestedView = profile.suggestedView ? profile.suggestedView.replace('-', ' ') : 'quality';

  const cards = [
    { label: 'Total Rows', value: Number(data.totalRows || 0).toLocaleString(), sub: 'records available', icon: 'bi-database', accent: accentList[0] },
    { label: 'Columns', value: data.columns.length, sub: 'fields detected', icon: 'bi-layout-three-columns', accent: accentList[1] },
    { label: 'Readiness', value: `${fmt(profile.score ?? 0)}%`, sub: `${suggestedView} view`, icon: 'bi-stars', accent: accentList[2] },
    { label: 'Completeness', value: `${fmt(data.completenessScore)}%`, sub: 'measured cells filled', icon: 'bi-check2-circle', accent: accentList[3] }
  ];

  if (profile.numericMeasureCount > 0) {
    cards.push({ label: 'Measures', value: profile.numericMeasureCount, sub: 'numeric fields', icon: 'bi-123', accent: accentList[0] });
  }
  if (profile.textDimensionCount > 0) {
    cards.push({ label: 'Dimensions', value: profile.textDimensionCount, sub: 'category fields', icon: 'bi-tags', accent: accentList[1] });
  }
  if (profile.dateColumnCount > 0) {
    cards.push({ label: 'Date Fields', value: profile.dateColumnCount, sub: 'time-aware fields', icon: 'bi-calendar3', accent: accentList[3] });
  }

  if (data.numericStats.length > 0) {
    const ns = data.numericStats[0];
    cards.push(
      { label: `Average - ${ns.column}`, value: fmt(ns.avg), sub: `range ${fmt(ns.min)} to ${fmt(ns.max)}`, icon: 'bi-calculator', accent: accentList[2] },
      { label: `Total - ${ns.column}`, value: fmt(ns.sum), sub: 'sum of non-null values', icon: 'bi-plus-square', accent: accentList[0] }
    );
  } else if (data.categoryData?.profile) {
    cards.push({
      label: 'Top Category Field',
      value: data.categoryData.profile.distinctCount,
      sub: `${data.categoryData.column} distinct values`,
      icon: 'bi-pie-chart',
      accent: accentList[1]
    });
  }

  cards.forEach(c => {
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.style.setProperty('--card-accent', c.accent);
    card.innerHTML = `
      <div class="stat-label">${escHtml(c.label)}</div>
      <div class="stat-value">${escHtml(c.value)}</div>
      <div class="stat-sub">${escHtml(c.sub)}</div>
      <i class="bi ${c.icon} stat-icon"></i>
    `;
    row.appendChild(card);
  });
}
function renderCharts(data) {
  // Destroy old charts
  Object.values(charts).forEach(c => c.destroy());
  charts = {};

  const grid = document.getElementById('chartsGrid');
  grid.innerHTML = '';
  appendQualityCard(grid, data);

  const chartDefaults = {
    plugins: {
      legend: { labels: { color: '#8892a4', font: { family: 'DM Mono', size: 11 } } }
    },
    scales: {
      x: { ticks: { color: '#8892a4', font: { family: 'DM Mono', size: 10 } }, grid: { color: '#252a38' } },
      y: { ticks: { color: '#8892a4', font: { family: 'DM Mono', size: 10 } }, grid: { color: '#252a38' } }
    }
  };

  // 1. Bar chart — numeric analytics metrics
  if (data.numericStats.length > 0) {
    const card = makeChartCard('Numeric Analytics — Smallest / Largest / Average');
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['numStats'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.numericStats.map(n => n.column),
        datasets: [
          { label: 'Smallest Value', data: data.numericStats.map(n => n.min), backgroundColor: '#4d9fff44', borderColor: '#4d9fff', borderWidth: 1.5 },
          { label: 'Average Value', data: data.numericStats.map(n => n.avg), backgroundColor: '#00e5a044', borderColor: '#00e5a0', borderWidth: 1.5 },
          { label: 'Largest Value', data: data.numericStats.map(n => n.max), backgroundColor: '#ffd16644', borderColor: '#ffd166', borderWidth: 1.5 }
        ]
      },
      options: { ...chartDefaults, responsive: true }
    });
  }

  // 2. Pie chart — category distribution
  if (data.categoryData && data.categoryData.data.length > 0) {
    const cat = data.categoryData;
    const card = makeChartCard(`Distribution - ${cat.column}`);
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    const colors = ['#00e5a0','#4d9fff','#ffd166','#ff6b6b','#c77dff','#06d6a0','#ef476f','#ffd166','#118ab2','#073b4c'];
    charts['category'] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cat.data.map(d => String(d.label).slice(0, 20)),
        datasets: [{ data: cat.data.map(d => d.count ?? d.item_count), backgroundColor: colors, borderColor: '#111318', borderWidth: 2 }]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'right', labels: { color: '#8892a4', font: { family: 'DM Mono', size: 11 }, padding: 12 } } }
      }
    });
  }

  // 3. Line chart — time series
  if (data.timeSeriesData && data.timeSeriesData.data.length > 0) {
    const ts = data.timeSeriesData;
    const card = makeChartCard(`${ts.valueColumn} over Time (${ts.dateColumn})`);
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['timeSeries'] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ts.data.map(d => d.period),
        datasets: [{
          label: ts.valueColumn,
          data: ts.data.map(d => d.total),
          borderColor: '#00e5a0',
          backgroundColor: '#00e5a015',
          borderWidth: 2,
          pointBackgroundColor: '#00e5a0',
          pointRadius: 3,
          fill: true,
          tension: 0.3
        }]
      },
      options: { ...chartDefaults, responsive: true }
    });
  }

  // 4. Horizontal bar — sum of numeric columns
  if (data.numericStats.length > 1) {
    const card = makeChartCard('Column Totals (Sum)');
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['sums'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.numericStats.map(n => n.column),
        datasets: [{
          label: 'Sum',
          data: data.numericStats.map(n => n.sum),
          backgroundColor: data.numericStats.map((_, i) =>
            ['#00e5a044','#4d9fff44','#ffd16644','#ff6b6b44','#c77dff44','#06d6a044'][i % 6]),
          borderColor: data.numericStats.map((_, i) =>
            ['#00e5a0','#4d9fff','#ffd166','#ff6b6b','#c77dff','#06d6a0'][i % 6]),
          borderWidth: 1.5
        }]
      },
      options: { ...chartDefaults, responsive: true, indexAxis: 'y' }
    });
  }

  if (grid.children.length === 0) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:13px;padding:20px">No chart data could be generated for this table (no numeric or categorical columns detected).</p>';
  }
}

function appendQualityCard(grid, data) {
  if (!data.columnQuality || data.columnQuality.length === 0) return;

  const sorted = [...data.columnQuality]
    .filter(c => c.nullCount > 0)
    .sort((a, b) => b.nullPercent - a.nullPercent)
    .slice(0, 5);

  const card = document.createElement('div');
  card.className = 'chart-card quality-card';
  const rows = sorted.length
    ? sorted.map(c => `
      <div class="quality-row">
        <span>${escHtml(c.column)}</span>
        <strong>${c.nullPercent}% null</strong>
      </div>
    `).join('')
    : '<div class="quality-empty">No missing values found in measured columns.</div>';

  card.innerHTML = `
    <div class="chart-card-title">Data Completeness</div>
    <div class="quality-score">${fmt(data.completenessScore)}%</div>
    <div class="quality-sub">complete across measured columns</div>
    <div class="quality-list">${rows}</div>
  `;
  grid.appendChild(card);
}

function makeChartCard(title) {
  const card = document.createElement('div');
  card.className = 'chart-card';
  card.innerHTML = `<div class="chart-card-title">${escHtml(title)}</div><canvas></canvas>`;
  return card;
}

function renderDataTable(rows, columns) {
  const wrap = document.getElementById('dataTableWrap');
  const empty = document.getElementById('dataEmpty');

  if (!rows || rows.length === 0) {
    wrap.innerHTML = '';
    empty.classList.remove('d-none');
    return;
  }
  empty.classList.add('d-none');

  const colNames = columns.map(c => c.COLUMN_NAME);
  let html = `<table class="data-table"><thead><tr>`;
  colNames.forEach(c => { html += `<th>${escHtml(c)}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    colNames.forEach(c => {
      const val = row[c];
      html += `<td title="${escHtml(String(val ?? ''))}">${escHtml(val == null ? 'NULL' : String(val))}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function exportSampleCsv() {
  if (!analyticsData || !analyticsData.sampleRows || analyticsData.sampleRows.length === 0) return;

  const columns = analyticsData.columns.map(c => c.COLUMN_NAME);
  const csvRows = [columns.map(csvCell).join(',')];
  analyticsData.sampleRows.forEach(row => {
    csvRows.push(columns.map(col => csvCell(row[col] ?? '')).join(','));
  });

  const blob = new Blob([csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const tableName = tableLabel(selectedTable).replace(/[^a-z0-9_-]+/gi, '_') || 'data';
  a.href = url;
  a.download = `${tableName}_sample.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = String(value).replace(/"/g, '""');
  return /[",\r\n]/.test(text) ? `"${text}"` : text;
}
// ── Helpers ────────────────────────────────────────────────────────────
function tableLabel(table) {
  if (!table) return '';
  if (typeof table === 'string') return table;
  return table.label || [table.schema, table.name].filter(Boolean).join('.') || String(table);
}

function tablePayload(table) {
  if (!table || typeof table === 'string') return table;
  return { schema: table.schema, name: table.name, label: tableLabel(table) };
}
async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return res.json();
}


function showError(el, msg) { el.textContent = msg; el.classList.remove('d-none'); }
function showSuccess(el, msg) { el.textContent = msg; el.classList.remove('d-none'); }
function hideEl(el) { el.classList.add('d-none'); }

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmt(n) {
  if (n === null || n === undefined) return '-';
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return Number(n).toLocaleString();
}

// ── AI INSIGHTS ────────────────────────────────────────────────────────
async function loadAIInsights(tableName) {
  const loading = document.getElementById('insightsLoading');
  const content = document.getElementById('insightsContent');
  const empty = document.getElementById('insightsEmpty');

  resetAIInsightCards();
  content.classList.add('d-none');
  empty.classList.add('d-none');
  loading.classList.remove('d-none');

  try {
    const res = await post('/api/analytics/executive-summary', { connInfo, tableName: tablePayload(tableName) });
    loading.classList.add('d-none');

    if (res.error) {
      empty.classList.remove('d-none');
      empty.querySelector('p').textContent = res.error;
      return;
    }

    if (!res.summary) {
      empty.classList.remove('d-none');
      empty.querySelector('p').textContent = 'No numeric data found to analyze.';
      return;
    }

    renderAIInsights(res);
    content.classList.remove('d-none');
  } catch (e) {
    console.error('AI Insights Error:', e);
    loading.classList.add('d-none');
    empty.classList.remove('d-none');
    empty.querySelector('p').textContent = 'Failed to generate AI insights.';
  }
}

function resetAIInsightCards() {
  ['summaryCard', 'metricsCard', 'anomaliesCard', 'trendsCard', 'columnAnalysisCard', 'recommendationsCard']
    .forEach(id => document.getElementById(id)?.classList.add('d-none'));
  ['summaryContent', 'metricsContent', 'anomaliesContent', 'trendsContent', 'columnAnalysisContent', 'recommendationsContent']
    .forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = ''; });

  const selector = document.getElementById('columnSelector');
  if (selector) selector.innerHTML = '<option value="">Select a column to analyze...</option>';
}
async function copyInsightsReport() {
  const report = buildInsightsReport();
  if (!report) return;

  try {
    await navigator.clipboard.writeText(report);
    flashAction('AI report copied to clipboard.');
  } catch (e) {
    console.error('Clipboard copy failed:', e);
    flashAction('Copy failed. Select the report text manually.');
  }
}

function buildInsightsReport() {
  if (!window.aiDetailedAnalysis || !selectedTable) return '';

  const lines = [
    `DataLens AI Report`,
    `Table: ${tableLabel(selectedTable)}`,
    `Generated: ${new Date().toLocaleString()}`,
    ''
  ];

  const summaryText = document.getElementById('summaryContent')?.innerText.trim();
  const trendsText = document.getElementById('trendsContent')?.innerText.trim();
  const anomaliesText = document.getElementById('anomaliesContent')?.innerText.trim();
  const recommendationsText = document.getElementById('recommendationsContent')?.innerText.trim();

  if (summaryText) lines.push('Executive Summary', summaryText, '');
  if (trendsText) lines.push('Trends', trendsText, '');
  if (anomaliesText) lines.push('Anomalies', anomaliesText, '');
  if (recommendationsText) lines.push('Recommendations', recommendationsText, '');

  return lines.join('\n');
}

function flashAction(message) {
  const existing = document.getElementById('actionToast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'actionToast';
  toast.className = 'action-toast';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2600);
}
function cleanInsightText(value) {
  return String(value || '')
    .replace(/^[^A-Za-z0-9]+/, '')
    .replace(/[\uD800-\uDFFF]/g, '')
    .trim();
}
function renderAIInsights(data) {
  const summary = data.summary;

  // Render Executive Summary
  const summaryCard = document.getElementById('summaryCard');
  const summaryContent = document.getElementById('summaryContent');
  summaryCard.classList.remove('d-none');

  let html = '<div class="insight-summary">';
  if (summary.dataQualityScore !== undefined) {
    html += `<p><strong>Data Quality Score:</strong> ${escHtml(summary.dataQualityScore)}%</p>`;
  }
  if (summary.keyMetrics && summary.keyMetrics.length > 0) {
    html += `<p><strong>Top ${summary.keyMetrics.length} Metrics:</strong></p>`;
    html += '<ul style="margin-left: 16px;">';
    summary.keyMetrics.forEach(m => {
      html += `
        <li><strong>${escHtml(m.column)}</strong>: Avg ${escHtml(m.value)}
            (Range: ${escHtml(m.range)}, Variation: ${escHtml(m.variation)})</li>
      `;
    });
    html += '</ul>';
  }
  if (summary.categoryMetrics && summary.categoryMetrics.length > 0) {
    html += '<p><strong>Best Category Fields:</strong></p>';
    html += '<ul style="margin-left: 16px;">';
    summary.categoryMetrics.forEach(m => {
      html += `<li><strong>${escHtml(m.column)}</strong>: ${escHtml(m.distinctCount)} distinct values, ${escHtml(m.coveragePercent)}% filled</li>`;
    });
    html += '</ul>';
  }
  html += '</div>';
  summaryContent.innerHTML = html;

  // Render Key Metrics Cards
  if (summary.keyMetrics && summary.keyMetrics.length > 0) {
    const metricsCard = document.getElementById('metricsCard');
    const metricsContent = document.getElementById('metricsContent');
    metricsCard.classList.remove('d-none');

    metricsContent.innerHTML = '';
    const colors = ['#00e5a0', '#4d9fff', '#ffd166'];
    summary.keyMetrics.forEach((m, idx) => {
      const card = document.createElement('div');
      card.className = 'metric-item';
      card.style.borderLeftColor = colors[idx % colors.length];
      card.innerHTML = `
        <div class="metric-label">${escHtml(m.column)}</div>
        <div class="metric-value">${escHtml(m.value)}</div>
        <div class="metric-detail">Range: ${escHtml(m.range)}</div>
        <div class="metric-detail">Variation: ${escHtml(m.variation)}</div>
      `;
      metricsContent.appendChild(card);
    });
  }

  // Render Anomalies
  if (summary.criticalAnomalies && summary.criticalAnomalies.length > 0) {
    const anomaliesCard = document.getElementById('anomaliesCard');
    const anomaliesContent = document.getElementById('anomaliesContent');
    anomaliesCard.classList.remove('d-none');

    let html = '<div class="anomaly-list">';
    summary.criticalAnomalies.forEach(a => {
      html += `
        <div class="anomaly-item">
          <i class="bi bi-exclamation-circle-fill"></i>
          <strong>${escHtml(a.column)}</strong>: ${a.count} anomalies detected
        </div>
      `;
    });
    html += '</div>';
    anomaliesContent.innerHTML = html;
  }

  // Render Trends
  if (summary.trends && summary.trends.length > 0) {
    const trendsCard = document.getElementById('trendsCard');
    const trendsContent = document.getElementById('trendsContent');
    trendsCard.classList.remove('d-none');

    let html = '<div class="trends-list">';
    summary.trends.forEach(t => {
      const icon = t.direction === 'upward' ? '↑' : '↓';
      const color = t.direction === 'upward' ? '#00e5a0' : '#ff6b6b';
      html += `
        <div class="trend-item" style="border-left-color: ${color}">
          <span style="font-size: 18px; color: ${color}">${icon}</span>
          <strong>${escHtml(t.column)}</strong>: 
          <strong style="color: ${color}">${t.direction === 'upward' ? 'Upward' : 'Downward'}</strong> trend 
          (${t.strength} strength)
        </div>
      `;
    });
    html += '</div>';
    trendsContent.innerHTML = html;
  }

  // Populate column selector for detailed analysis
  if (data.detailedAnalysis && data.detailedAnalysis.length > 0) {
    const selector = document.getElementById('columnSelector');
    data.detailedAnalysis.forEach(col => {
      const option = document.createElement('option');
      option.value = col.column;
      option.textContent = col.column;
      selector.appendChild(option);
    });

    // Auto-select first column
    if (data.detailedAnalysis.length > 0) {
      selector.value = data.detailedAnalysis[0].column;
      displayColumnAnalysis(data.detailedAnalysis[0]);
      document.getElementById('columnAnalysisCard').classList.remove('d-none');
    }
  }

  // Render Recommendations
  if (summary.recommendations && summary.recommendations.length > 0) {
    const recommendationsCard = document.getElementById('recommendationsCard');
    const recommendationsContent = document.getElementById('recommendationsContent');
    recommendationsCard.classList.remove('d-none');

    let html = '<div class="recommendations-list" style="padding: 12px;">';
    summary.recommendations.forEach(r => {
      html += `<div style="margin-bottom: 12px; padding: 8px; background: #1a1d2e; border-left: 3px solid #ffd166; border-radius: 4px;">
        <i class="bi bi-lightbulb" style="color: #ffd166; margin-right: 8px;"></i>
        ${escHtml(cleanInsightText(r))}
      </div>`;
    });
    html += '</div>';
    recommendationsContent.innerHTML = html;
  }

  // Store detailed analysis for later use
  window.aiDetailedAnalysis = data.detailedAnalysis;
}


function renderActionList(title, items) {
  if (!items || items.length === 0) return '';
  return `
    <div class="anomaly-action-group">
      <strong>${escHtml(title)}</strong>
      <ul>${items.map(item => `<li>${escHtml(cleanInsightText(item))}</li>`).join('')}</ul>
    </div>
  `;
}
function displayColumnAnalysis(analysis) {
  const content = document.getElementById('columnAnalysisContent');

  let html = '<div class="column-analysis">';
  
  // Statistics
  html += '<h4 style="margin-top: 12px; margin-bottom: 8px;">Statistics</h4>';
  html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
  html += `<div><strong>Count:</strong> ${analysis.stats.count}</div>`;
  html += `<div><strong>Min:</strong> ${fmt(analysis.stats.min)}</div>`;
  html += `<div><strong>Max:</strong> ${fmt(analysis.stats.max)}</div>`;
  html += `<div><strong>Avg:</strong> ${fmt(analysis.stats.avg)}</div>`;
  html += `<div><strong>Median:</strong> ${fmt(analysis.stats.median)}</div>`;
  html += `<div><strong>Std Dev:</strong> ${fmt(analysis.stats.stdDev)}</div>`;
  html += '</div>';

  // Trend Information
  if (analysis.trend) {
    html += '<h4 style="margin-top: 16px; margin-bottom: 8px;">Trend Analysis</h4>';
    html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
    html += `<div><strong>Direction:</strong> ${analysis.trend.trend}</div>`;
    html += `<div><strong>Slope:</strong> ${analysis.trend.slope}</div>`;
    html += `<div><strong>Strength:</strong> ${analysis.trend.strength}</div>`;
    html += `<div><strong>Confidence:</strong> ${analysis.trend.confidence}%</div>`;
    if (analysis.trend.prediction !== undefined) {
      html += `<div style="grid-column: 1/-1;"><strong>Forecast (Next Value):</strong> ${fmt(analysis.trend.prediction)}</div>`;
    }
    html += '</div>';
  }

  // Anomalies
  if (analysis.anomalies && analysis.anomalies.length > 0) {
    html += `<h4 style="margin-top: 16px; margin-bottom: 8px;">Anomalies Detected (${analysis.anomalies.length})</h4>`;
    html += '<div style="max-height: 200px; overflow-y: auto;">';
    analysis.anomalies.slice(0, 10).forEach(a => {
      html += `<div style="padding: 8px; background: #1a1d2e; margin-bottom: 4px; border-radius: 3px;">
        Value: <strong>${fmt(a.value)}</strong> (Z-Score: ${a.zScore.toFixed(2)})
      </div>`;
    });
    if (analysis.anomalies.length > 10) {
      html += `<div style="color: #8892a4; font-size: 12px; padding: 8px;">... and ${analysis.anomalies.length - 10} more</div>`;
    }
    html += '</div>';
  }


  if (analysis.anomaliesDetailed && analysis.anomaliesDetailed.length > 0) {
    const topDetail = analysis.anomaliesDetailed[0];
    html += '<h4 style="margin-top: 16px; margin-bottom: 8px;">How To Investigate The Main Anomaly</h4>';
    html += `<div class="anomaly-detail-panel">
      <div><strong>Severity:</strong> ${escHtml(topDetail.severity)} ${escHtml(topDetail.type)} anomaly</div>
      <div><strong>Row position:</strong> ${escHtml(Number(topDetail.rowIndex) + 1)}</div>
      <div><strong>Actual value:</strong> ${fmt(topDetail.actualValue)}</div>
      <div><strong>Expected range:</strong> ${escHtml(topDetail.expectedRange)}</div>
      <div><strong>Impact:</strong> ${escHtml(topDetail.impact || topDetail.deviation)}</div>
      <div><strong>Surrounding average:</strong> ${fmt(topDetail.surroundingAverage)}</div>
    </div>`;
    html += renderActionList('Likely causes', topDetail.likelyCauses);
    html += renderActionList('Validation checks', topDetail.validationChecks);
    html += renderActionList('Fix steps', topDetail.fixSteps);
    html += renderActionList('Business questions', topDetail.businessQuestions);
    html += renderActionList('Decision guide', topDetail.decisionGuide);
  }
  html += '</div>';
  content.innerHTML = html;
}

function analyzeSelectedColumn() {
  const selector = document.getElementById('columnSelector');
  const columnName = selector.value;

  if (!columnName || !window.aiDetailedAnalysis) return;

  const analysis = window.aiDetailedAnalysis.find(a => a.column === columnName);
  if (analysis) {
    displayColumnAnalysis(analysis);
  }
}
