/* DataLens - Frontend Application Logic */

// State
let connInfo = null;          // DB connection details
let availableTables = [];
let tableListEmptyMessage = 'No matching tables found.';
let cleanedMode = false;
let selectedTable = null;
let analyticsData = null;
let charts = {};              // Chart.js instances
let dbType = 'sqlserver';     // Database type (sqlserver or mysql)
let insightMode = 'executive';
let insightEngine = 'smart';
let smartInsightsResult = null;
let currentTheme = 'industrial';
const THEME_STORAGE_KEY = 'datalens-color-theme';
const COLOR_THEMES = {
  industrial: ['#00e5a0', '#4d9fff', '#ffd166', '#ff6b6b', '#c77dff', '#06d6a0', '#ef476f', '#118ab2'],
  ocean: ['#38bdf8', '#22d3ee', '#facc15', '#fb7185', '#818cf8', '#2dd4bf', '#f472b6', '#0ea5e9'],
  light: ['#2563eb', '#0891b2', '#ca8a04', '#dc2626', '#7c3aed', '#16a34a', '#db2777', '#0284c7'],
  forest: ['#4d7c0f', '#0f766e', '#a16207', '#b91c1c', '#15803d', '#0369a1', '#65a30d', '#be185d']
};
const API_BASE_URL = window.location.protocol === 'file:' ? 'http://127.0.0.1:3000' : '';

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

// Init
window.addEventListener('DOMContentLoaded', () => {
  initTheme();
  loadDatabaseConfig();
  showApp();
});

function initTheme() {
  const savedTheme = getStoredTheme();
  applyColorTheme(COLOR_THEMES[savedTheme] ? savedTheme : currentTheme);
}

function getStoredTheme() {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) || localStorage.getItem('datalens-color-palette');
  } catch (e) {
    console.warn('Theme storage is unavailable:', e);
    return null;
  }
}

function saveTheme(name) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, name);
  } catch (e) {
    console.warn('Theme preference could not be saved:', e);
  }
}

function onThemeChange() {
  const selected = document.getElementById('themeSelector')?.value || 'industrial';
  applyColorTheme(selected);
  if (analyticsData) renderDashboard(analyticsData);
}

function applyColorTheme(name) {
  currentTheme = COLOR_THEMES[name] ? name : 'industrial';
  if (currentTheme === 'industrial') {
    document.body.removeAttribute('data-theme');
  } else {
    document.body.dataset.theme = currentTheme;
  }
  saveTheme(currentTheme);

  const selector = document.getElementById('themeSelector');
  if (selector) selector.value = currentTheme;
}

function getThemeColors() {
  return COLOR_THEMES[currentTheme] || COLOR_THEMES.industrial;
}

function cssVar(name) {
  return getComputedStyle(document.body).getPropertyValue(name).trim();
}

function withAlpha(hex, alphaHex) {
  return `${hex}${alphaHex}`;
}

async function loadDatabaseConfig() {
  try {
    const res = await fetch(apiUrl('/api/db/config'));
    const data = await res.json();
    dbType = data.dbType || 'sqlserver';
    document.getElementById('dbTypeSelector').value = dbType;
    updateFormForDatabaseType();
  } catch (e) {
    console.error('Failed to load database config:', e);
  }
}

function onDatabaseTypeChange() {
  dbType = document.getElementById('dbTypeSelector').value;
  updateFormForDatabaseType();
  resetLoadedData();
  showPanel('connect');
}

function updateFormForDatabaseType() {
  const isMySQL = dbType === 'mysql';
  const defaultPort = isMySQL ? 3306 : 1433;
  const dbLabel = isMySQL ? 'MySQL' : 'SQL Server';
  const userPlaceholder = isMySQL ? 'root' : 'sa';
  
  // Update form title and labels
  document.getElementById('dbTypeLabel').textContent = `${dbLabel} Details`;
  
  // Set default port (only if it's still the old default)
  const portInput = document.getElementById('dbPort');
  if (portInput.value == 1433 || portInput.value == 3306) {
    portInput.value = defaultPort;
  }
  
  // Update placeholder text
  document.getElementById('dbUser').placeholder = userPlaceholder;
  
  const serverField = document.getElementById('dbServer');
  serverField.placeholder = isMySQL ? 'localhost' : 'localhost or 192.168.1.10';
  
  // Hide/show SQL Server specific options
  const headerCopy = document.querySelector('#panelConnect .panel-header p');
  if (headerCopy) {
    headerCopy.textContent = `Enter your ${dbLabel} credentials to get started`;
  }

  const sqlServerOptions = document.getElementById('sqlServerOptions');
  if (sqlServerOptions) {
    sqlServerOptions.style.display = isMySQL ? 'none' : 'flex';
  }
}

function resetLoadedData() {
  connInfo = null;
  availableTables = [];
  tableListEmptyMessage = 'No matching tables found.';
  selectedTable = null;
  analyticsData = null;
  window.smartDetailedAnalysis = null;
  smartInsightsResult = null;

  Object.values(charts).forEach(c => c.destroy());
  charts = {};

  document.getElementById('tableListCard').style.display = 'none';
  document.getElementById('tableList').innerHTML = '';
  document.getElementById('tableCountBadge').textContent = '0';
  document.getElementById('dbBadge').classList.add('d-none');
  document.getElementById('dbBadgeText').textContent = 'Not connected';
  document.getElementById('dashContent').classList.add('d-none');
  document.getElementById('dashLoading').classList.add('d-none');
  document.getElementById('dashEmpty').classList.remove('d-none');
  document.querySelector('#dashEmpty p').textContent = 'No table selected. Go to Connect and click a table.';
  document.getElementById('dashTableName').textContent = 'Select a table to view analytics';
  document.getElementById('dataTableWrap').innerHTML = '';
  document.getElementById('dataEmpty').classList.remove('d-none');
  document.getElementById('insightsContent').classList.add('d-none');
  document.getElementById('insightsLoading').classList.add('d-none');
  document.getElementById('insightsEmpty').classList.remove('d-none');
  document.querySelector('#insightsEmpty p').textContent = 'No table selected. Connect and select an analytics-ready table to use Insight Engine.';
  resetSmartInsightCards();
}
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

// Navigation
function showPanel(name) {
  if (['dashboard', 'insights', 'data'].includes(name) && selectedTable && !isAnalyticsReadyTable(selectedTable)) {
    showPanel('connect');
    showError(document.getElementById('connectError'), blockedTableMessage(selectedTable));
    return;
  }
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const panelMap = { connect: 'panelConnect', dashboard: 'panelDashboard', insights: 'panelInsights', data: 'panelData' };
  const titleMap = { connect: 'Connect to Database', dashboard: 'Analytics Dashboard', insights: 'Insight Engine', data: 'Data Preview' };

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

  // Load Insight Engine when panel is opened
  if (name === 'insights' && selectedTable) {
    loadSmartInsights(selectedTable);
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

// DB Connect
async function doConnect() {
  const server   = document.getElementById('dbServer').value.trim();
  const port     = document.getElementById('dbPort').value.trim();
  const database = document.getElementById('dbName').value.trim();
  const username = document.getElementById('dbUser').value.trim();
  const password = document.getElementById('dbPass').value;
  const encrypt  = document.getElementById('dbEncrypt').checked;
  const trustCert= document.getElementById('dbTrustCert').checked;
  const dbTypeVal = document.getElementById('dbTypeSelector')?.value || dbType;
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

  connInfo = { server, port, database, username, password, encrypt, trustCert, dbType: dbTypeVal };

  try {
    const res = await post('/api/db/connect', connInfo);
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';

    if (res.error) return showError(errEl, res.error);

    availableTables = res.tables || [];
    const readyCount = Number(res.analyticsReadyCount ?? res.tableCount ?? 0);
    const safeCount = Number(res.safeTableCount ?? availableTables.length);
    const sensitiveCount = Number(res.sensitiveTableCount || 0);
    const filtered = Number(res.filteredTableCount || 0);
    const rawCount = Number(res.rawTableCount ?? (safeCount + filtered));
    const hiddenText = filtered ? `, ${filtered} sensitive table(s) hidden` : '';
    const blockedText = sensitiveCount ? `, ${sensitiveCount} sensitive-looking table(s) shown as blocked` : '';
    const warningText = res.warning ? ` ${res.warning}${res.discoveryError ? ` Details: ${res.discoveryError}` : ''}` : '';
    const countText = rawCount > 0
      ? `${readyCount} ready of ${safeCount} visible table(s)${hiddenText}${blockedText}`
      : 'no user tables found';
    tableListEmptyMessage = res.warning || (rawCount > 0
      ? 'No tables match your current search.'
      : 'Connected, but no user tables were found for this database/account.');
    showSuccess(sucEl, `Connected to "${res.database}" - ${countText}.${warningText}`);
    // Show DB badge in topbar
    const badge = document.getElementById('dbBadge');
    badge.classList.remove('d-none');
    document.getElementById('dbBadgeText').textContent = `${res.database} (${readyCount} ready tables)`;
    renderTableList(availableTables);
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';
    showError(errEl, e.message || 'DataLens backend is not reachable.');
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
  const readyVisible = filteredTables.filter(t => t.profile?.usable).length;

  badge.textContent = `${readyVisible}/${filteredTables.length}`;
  list.innerHTML = '';

  if (filteredTables.length === 0) {
    list.innerHTML = `<p style="color:var(--text-muted);font-size:12px;padding:8px">${escHtml(search ? 'No tables match your current search.' : tableListEmptyMessage)}</p>`;
  } else {
    filteredTables.forEach(t => {
      const item = document.createElement('div');
      const profile = t.profile || {};
      const usable = profile.usable !== false;
      const healthLabel = profile.healthLabel || (usable ? 'Ready' : 'Blocked');
      const details = [
        profile.rowCount !== undefined ? `${fmt(profile.rowCount)} rows` : null,
        profile.suggestedView ? profile.suggestedView.replace('-', ' ') : null,
        profile.healthReasons?.[0] || profile.reason || null
      ].filter(Boolean).join(' / ');
      const selectedClass = tableLabel(t) === tableLabel(selectedTable) ? ' selected' : '';
      item.className = `table-item${selectedClass}${usable ? '' : ' table-item-disabled'}`;
      item.innerHTML = `
        <i class="bi ${usable ? 'bi-table' : 'bi-shield-exclamation'}"></i>
        <span class="table-item-main">
          <span>${escHtml(tableLabel(t))}</span>
          ${details ? `<small>${escHtml(details)}</small>` : ''}
        </span>
        <span class="table-health-pill ${healthClass(healthLabel)}" title="${escHtml(profile.recommendedAction || profile.reason || '')}">
          ${escHtml(healthLabel)} ${profile.score !== undefined ? escHtml(profile.score) + '%' : ''}
        </span>
      `;
      if (usable) {
        item.addEventListener('click', () => selectTable(t, item));
      } else {
        item.setAttribute('aria-disabled', 'true');
        item.title = blockedTableMessage(t);
        item.addEventListener('click', () => showError(document.getElementById('connectError'), blockedTableMessage(t)));
      }
      list.appendChild(item);
    });
  }

  card.style.display = 'block';
}

function healthClass(label) {
  const value = String(label || '').toLowerCase();
  if (value.includes('excellent')) return 'excellent';
  if (value.includes('good')) return 'good';
  if (value.includes('fair')) return 'fair';
  return 'blocked';
}

function isAnalyticsReadyTable(table) {
  const profile = table?.profile || {};
  return !!table && profile.usable !== false && table.analyticsReady !== false;
}

function blockedTableMessage(table) {
  const profile = table?.profile || {};
  return profile.recommendedAction || profile.reason || profile.healthReasons?.[0] || 'This table is blocked for analytics.';
}
async function onInsightModeChange() {
  insightMode = document.getElementById('insightModeSelector')?.value || 'executive';
  if (selectedTable && document.getElementById('panelInsights')?.classList.contains('active')) {
    await loadSmartInsights(selectedTable);
  }
}
async function onInsightEngineChange() {
  insightEngine = document.getElementById('insightEngineSelector')?.value || 'smart';
  if (selectedTable && document.getElementById('panelInsights')?.classList.contains('active')) {
    await loadSmartInsights(selectedTable);
  }
}
function filterTableList() {
  renderTableList(availableTables);
}

async function refreshSelectedTable() {
  if (!selectedTable) return;
  await loadAnalytics(selectedTable);
}

async function selectTable(tableName, itemEl) {
  if (!isAnalyticsReadyTable(tableName)) {
    showError(document.getElementById('connectError'), blockedTableMessage(tableName));
    return;
  }

  document.querySelectorAll('.table-item').forEach(i => i.classList.remove('selected'));
  itemEl.classList.add('selected');
  selectedTable = tableName;

  // Navigate to dashboard and load analytics
  showPanel('dashboard');
  await loadAnalytics(tableName);
}

// Analytics
async function loadAnalytics(tableName) {
  const loading = document.getElementById('dashLoading');
  const content = document.getElementById('dashContent');
  const empty   = document.getElementById('dashEmpty');

  resetSmartInsightCards();
  content.classList.add('d-none');
  empty.classList.add('d-none');
  loading.classList.remove('d-none');
  document.getElementById('dashTableName').textContent = `Table: ${tableLabel(tableName)}`;

  try {
    const res = await post('/api/analytics/table', { connInfo, dbType: connInfo?.dbType || dbType, tableName: tablePayload(tableName), cleanedMode });
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
    empty.querySelector('p').textContent = e.message || 'Failed to load analytics.';
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
  const themeColors = getThemeColors();
  const textColor = cssVar('--text-secondary') || '#8892a4';
  const gridColor = cssVar('--border') || '#252a38';
  const surfaceColor = cssVar('--bg-surface') || '#111318';

  const chartDefaults = {
    plugins: {
      legend: { labels: { color: textColor, font: { family: 'DM Mono', size: 11 } } }
    },
    scales: {
      x: { ticks: { color: textColor, font: { family: 'DM Mono', size: 10 } }, grid: { color: gridColor } },
      y: { ticks: { color: textColor, font: { family: 'DM Mono', size: 10 } }, grid: { color: gridColor } }
    }
  };

  // 1. Bar chart - numeric analytics metrics
  if (data.numericStats.length > 0) {
    const card = makeChartCard('Numeric Analytics - Smallest / Largest / Average');
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['numStats'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.numericStats.map(n => n.column),
        datasets: [
          { label: 'Smallest Value', data: data.numericStats.map(n => n.min), backgroundColor: withAlpha(themeColors[1], '44'), borderColor: themeColors[1], borderWidth: 1.5 },
          { label: 'Average Value', data: data.numericStats.map(n => n.avg), backgroundColor: withAlpha(themeColors[0], '44'), borderColor: themeColors[0], borderWidth: 1.5 },
          { label: 'Largest Value', data: data.numericStats.map(n => n.max), backgroundColor: withAlpha(themeColors[2], '44'), borderColor: themeColors[2], borderWidth: 1.5 }
        ]
      },
      options: { ...chartDefaults, responsive: true }
    });
  }

  // 2. Pie chart - category distribution
  if (data.categoryData && data.categoryData.data.length > 0) {
    const cat = data.categoryData;
    const card = makeChartCard(`Distribution - ${cat.column}`);
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['category'] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cat.data.map(d => String(d.label).slice(0, 20)),
        datasets: [{ data: cat.data.map(d => d.count ?? d.item_count), backgroundColor: themeColors, borderColor: surfaceColor, borderWidth: 2 }]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'right', labels: { color: textColor, font: { family: 'DM Mono', size: 11 }, padding: 12 } } }
      }
    });
  }

  // 3. Line chart - time series
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
          borderColor: themeColors[0],
          backgroundColor: withAlpha(themeColors[0], '15'),
          borderWidth: 2,
          pointBackgroundColor: themeColors[0],
          pointRadius: 3,
          fill: true,
          tension: 0.3
        }]
      },
      options: { ...chartDefaults, responsive: true }
    });
  }

  // 4. Horizontal bar - sum of numeric columns
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
            withAlpha(themeColors[i % themeColors.length], '44')),
          borderColor: data.numericStats.map((_, i) =>
            themeColors[i % themeColors.length]),
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
// Helpers
function tableLabel(table) {
  if (!table) return '';
  if (typeof table === 'string') return table;
  return table.label || [table.schema, table.name].filter(Boolean).join('.') || String(table);
}

async function onCleanedModeToggle() {
  const el = document.getElementById('cleanedModeToggle');
  cleanedMode = !!el?.checked;

  // If a table is already selected, immediately refresh dashboard data
  if (selectedTable) {
    await loadAnalytics(selectedTable);
  }
}


function tablePayload(table) {
  if (!table || typeof table === 'string') return table;
  return { schema: table.schema, name: table.name, label: tableLabel(table) };
}
async function post(url, body) {
  let res;
  try {
    res = await fetch(apiUrl(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  } catch (error) {
    throw new Error(window.location.protocol === 'file:' ? 'This page was opened as a file. Open http://127.0.0.1:3000 instead, or restart DataLens so it serves the app through the local backend.' : 'DataLens backend is not reachable. Restart DataLens or run the local server on http://127.0.0.1:3000.');
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed with status ${res.status}.`);
  }
  return data;
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



async function loadSmartInsights(tableName) {
  const loading = document.getElementById('insightsLoading');
  const content = document.getElementById('insightsContent');
  const empty = document.getElementById('insightsEmpty');

  resetSmartInsightCards();
  content.classList.add('d-none');
  empty.classList.add('d-none');
  loading.classList.remove('d-none');

  try {
    insightMode = document.getElementById('insightModeSelector')?.value || insightMode || 'executive';
    insightEngine = document.getElementById('insightEngineSelector')?.value || insightEngine || 'smart';
    const useAiInsights = insightEngine === 'ai';
    const res = await post('/api/analytics/executive-summary', { connInfo, dbType: connInfo?.dbType || dbType, tableName: tablePayload(tableName), cleanedMode, insightMode, insightEngine, useAiInsights });

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

    smartInsightsResult = res;
    renderSmartInsights(res);
    content.classList.remove('d-none');
  } catch (e) {
    console.error('Insight Engine Error:', e);
    loading.classList.add('d-none');
    empty.classList.remove('d-none');
    empty.querySelector('p').textContent = e.message || 'Failed to generate insights.';
  }
}

function resetSmartInsightCards() {
  ['summaryCard', 'metricsCard', 'anomaliesCard', 'trendsCard', 'columnAnalysisCard', 'recommendationsCard']
    .forEach(id => document.getElementById(id)?.classList.add('d-none'));

  const recommendationsTitle = document.querySelector('#recommendationsCard h3');
  if (recommendationsTitle) recommendationsTitle.innerHTML = '<i class="bi bi-lightbulb"></i> Recommendations';
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
    flashAction('Insight Engine report copied to clipboard.');
  } catch (e) {
    console.error('Clipboard copy failed:', e);
    flashAction('Copy failed. Select the report text manually.');
  }
}

function buildInsightsReport() {
  const data = smartInsightsResult;
  if (!data?.summary || !selectedTable) return '';

  const summary = data.summary;
  const modeLabel = summary.modeLabel || insightModeLabel(summary.mode || insightMode);
  const lines = [
    `# DataLens Insight Engine Report`,
    ``,
    `**Table:** ${tableLabel(selectedTable)}`,
    `**Mode:** ${modeLabel}`,
    `**Generated:** ${new Date().toLocaleString()}`,
    ``
  ];

  if (summary.narrativeText) {
    lines.push(`## Narrative`, summary.narrativeText, ``);
  }

  (summary.reportSections || []).forEach(section => {
    lines.push(`## ${section.title}`);
    (section.items || []).forEach(item => lines.push(`- ${cleanInsightText(item)}`));
    lines.push('');
  });

  if (summary.recommendations?.length) {
    lines.push('## Recommendations');
    summary.recommendations.forEach(item => lines.push(`- ${cleanInsightText(item)}`));
    lines.push('');
  }

  return lines.join('\n');
}

function exportInsightsMarkdown() {
  const report = buildInsightsReport();
  if (!report) return;

  const blob = new Blob([report], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const tableName = tableLabel(selectedTable).replace(/[^a-z0-9_-]+/gi, '_') || 'table';
  const mode = (smartInsightsResult?.summary?.mode || insightMode || 'executive').replace(/[^a-z0-9_-]+/gi, '_');
  a.href = url;
  a.download = `${tableName}_${mode}_smart_insights.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  flashAction('Insight Engine report exported.');
}
async function exportInsightsPdf() {
  if (!smartInsightsResult?.summary || !selectedTable) return;

  try {
    const res = await fetch(apiUrl('/api/analytics/export-pdf'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tableName: tableLabel(selectedTable),
        summary: smartInsightsResult.summary,
        profile: smartInsightsResult.profile || null
      })
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      flashAction(error.error || 'PDF export failed.');
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const tableName = tableLabel(selectedTable).replace(/[^a-z0-9_-]+/gi, '_') || 'table';
    const mode = (smartInsightsResult.summary.mode || insightMode || 'executive').replace(/[^a-z0-9_-]+/gi, '_');
    a.href = url;
    a.download = `${tableName}_${mode}_smart_insights.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    flashAction('Insight Engine PDF exported.');
  } catch (e) {
    console.error('PDF export failed:', e);
    flashAction('PDF export failed. Is the server running?');
  }
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
function renderSmartInsights(data) {
  const summary = data.summary;
  const themeColors = getThemeColors();
  const mode = summary.mode || insightMode || 'executive';
  const modeLabel = summary.modeLabel || insightModeLabel(mode);

  // Render Executive Summary
  const summaryCard = document.getElementById('summaryCard');
  const summaryContent = document.getElementById('summaryContent');
  const summaryTitle = summaryCard.querySelector('h3');
  if (summaryTitle) summaryTitle.innerHTML = `<i class="bi bi-briefcase-fill"></i> ${escHtml(modeLabel)}`;
  summaryCard.classList.remove('d-none');

  let html = '<div class="insight-summary">';
  if (modeLabel) {
    const engineLabel = summary.insightEngine === 'ai' ? 'AI Analysis' : 'Smart Analysis';
    html += `<p><strong>Engine:</strong> ${escHtml(engineLabel)}</p>`;
    html += `<p><strong>Mode:</strong> ${escHtml(modeLabel)}</p>`;
  }
  if (summary.dataQualityScore !== undefined) {
    html += `<p><strong>Data Quality Score:</strong> ${escHtml(summary.dataQualityScore)}%</p>`;
  }
  if (summary.llmStatus) {
    html += `<p><strong>Local AI:</strong> ${escHtml(summary.llmStatus)}</p>`;
  }
  if (summary.narrativeText) {
    html += `<div class="narrative-text">
      <p><strong>Narrative:</strong></p>
      <pre style="white-space: pre-wrap; font-family: inherit; margin: 0;">${escHtml(summary.narrativeText)}</pre>
    </div>`;
  }

  if (summary.keyObservations && summary.keyObservations.length > 0) {
    html += '<p><strong>Key Observations:</strong></p><ul style="margin-left: 16px;">';
    summary.keyObservations.forEach(item => {
      html += `<li>${escHtml(cleanInsightText(item))}</li>`;
    });
    html += '</ul>';
  }


  html += '</div>';
  summaryContent.innerHTML = html;

  // Render Key Metrics Cards
  if (modeAllowsCard(mode, 'metrics') && summary.keyMetrics && summary.keyMetrics.length > 0) {
    const metricsCard = document.getElementById('metricsCard');
    const metricsContent = document.getElementById('metricsContent');
    metricsCard.classList.remove('d-none');

    metricsContent.innerHTML = '';
    const colors = [themeColors[0], themeColors[1], themeColors[2]];
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
  if (modeAllowsCard(mode, 'anomalies') && summary.criticalAnomalies && summary.criticalAnomalies.length > 0) {
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

  if (summary.reportSections && summary.reportSections.length > 0) {
    renderReportSectionsCard(reportSectionsTitle(mode), reportSectionsIcon(mode), summary.reportSections);
  }

  // Render Trends
  if (modeAllowsCard(mode, 'trends') && summary.trends && summary.trends.length > 0) {
    const trendsCard = document.getElementById('trendsCard');
    const trendsContent = document.getElementById('trendsContent');
    trendsCard.classList.remove('d-none');

    let html = '<div class="trends-list">';
    summary.trends.forEach(t => {
      const icon = t.direction === 'upward' ? '&uarr;' : '&darr;';
      const color = t.direction === 'upward' ? themeColors[0] : themeColors[3];
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
  if (modeAllowsCard(mode, 'columns') && data.detailedAnalysis && data.detailedAnalysis.length > 0) {
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
  if (!summary.reportSections?.length && summary.recommendations && summary.recommendations.length > 0) {
    const recommendationsCard = document.getElementById('recommendationsCard');
    const recommendationsContent = document.getElementById('recommendationsContent');
    recommendationsCard.classList.remove('d-none');

    let html = '<div class="recommendations-list" style="padding: 12px;">';
    summary.recommendations.forEach(r => {
      html += `<div style="margin-bottom: 12px; padding: 8px; background: var(--bg-hover); border-left: 3px solid var(--accent4); border-radius: 4px;">
        <i class="bi bi-lightbulb" style="color: var(--accent4); margin-right: 8px;"></i>
        ${escHtml(cleanInsightText(r))}
      </div>`;
    });
    html += '</div>';
    recommendationsContent.innerHTML = html;
  }

  orderSmartInsightCards(mode);

  // Store detailed analysis for later use
  window.smartDetailedAnalysis = data.detailedAnalysis;
}


function reportSectionsHtml(sections) {
  let html = '<div class="report-section-grid">';
  sections.forEach(section => {
    html += `<section class="report-section"><h4>${escHtml(section.title)}</h4><ul>`;
    (section.items || []).forEach(item => {
      html += `<li>${escHtml(cleanInsightText(item))}</li>`;
    });
    html += '</ul></section>';
  });
  html += '</div>';
  return html;
}

function renderReportSectionsCard(title, icon, sections) {
  const card = document.getElementById('recommendationsCard');
  const content = document.getElementById('recommendationsContent');
  const cardTitle = card?.querySelector('h3');
  if (!card || !content) return;

  if (cardTitle) cardTitle.innerHTML = `<i class="bi ${icon}"></i> ${escHtml(title)}`;
  content.innerHTML = reportSectionsHtml(sections);
  card.classList.remove('d-none');
}

function reportSectionsTitle(mode) {
  const titles = {
    executive: 'Decision Brief',
    quality: 'Quality Review Details',
    anomaly: 'Investigation Details',
    forecast: 'Forecast Readiness Details',
    kpi: 'KPI Planning Details'
  };
  return titles[mode] || 'Insight Details';
}

function reportSectionsIcon(mode) {
  const icons = {
    executive: 'bi-clipboard-data',
    quality: 'bi-shield-check',
    anomaly: 'bi-search',
    forecast: 'bi-graph-up-arrow',
    kpi: 'bi-bullseye'
  };
  return icons[mode] || 'bi-lightbulb';
}
function orderSmartInsightCards(mode) {
  const content = document.getElementById('insightsContent');
  if (!content) return;

  const orders = {
    executive: ['summaryCard', 'metricsCard', 'anomaliesCard', 'trendsCard', 'recommendationsCard', 'columnAnalysisCard'],
    quality: ['summaryCard', 'recommendationsCard'],
    anomaly: ['summaryCard', 'anomaliesCard', 'recommendationsCard', 'columnAnalysisCard'],
    forecast: ['summaryCard', 'trendsCard', 'recommendationsCard'],
    kpi: ['summaryCard', 'metricsCard', 'recommendationsCard']
  };
  const order = orders[mode] || orders.executive;

  order.forEach(id => {
    const card = document.getElementById(id);
    if (card && !card.classList.contains('d-none')) content.appendChild(card);
  });
}
function insightModeLabel(mode) {
  const labels = {
    executive: 'Executive Summary',
    quality: 'Data Quality Review',
    anomaly: 'Anomaly Investigation',
    forecast: 'Forecast Readiness',
    kpi: 'Business KPI Suggestions'
  };
  return labels[mode] || labels.executive;
}

function modeAllowsCard(mode, card) {
  const visible = {
    executive: ['metrics', 'anomalies', 'trends', 'columns'],
    quality: [],
    anomaly: ['anomalies', 'columns'],
    forecast: ['trends'],
    kpi: ['metrics']
  };
  return (visible[mode] || visible.executive).includes(card);
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

  if (analysis.insights && analysis.insights.length > 0) {
    html += '<h4 style="margin-top: 12px; margin-bottom: 8px;">Insights</h4>';
    html += '<ul class="column-insight-list">';
    analysis.insights.forEach(item => {
      html += `<li>${escHtml(cleanInsightText(item))}</li>`;
    });
    html += '</ul>';
  }

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
      html += `<div style="padding: 8px; background: var(--bg-hover); margin-bottom: 4px; border-radius: 3px;">
        Value: <strong>${fmt(a.value)}</strong> (Z-Score: ${a.zScore.toFixed(2)})
      </div>`;
    });
    if (analysis.anomalies.length > 10) {
      html += `<div class="analysis-muted-note">... and ${analysis.anomalies.length - 10} more</div>`;
    }
    html += '</div>';
  }


  if (analysis.anomaliesDetailed && analysis.anomaliesDetailed.length > 0) {
    const topDetail = analysis.anomaliesDetailed[0];
    html += '<h4 style="margin-top: 16px; margin-bottom: 8px;">How To Investigate The Main Anomaly</h4>';
    html += `<div class="anomaly-detail-panel">
      <div class="anomaly-detail-item"><span>Severity</span><strong>${escHtml(topDetail.severity)} ${escHtml(topDetail.type)} anomaly</strong></div>
      <div class="anomaly-detail-item"><span>Row position</span><strong>${escHtml(Number(topDetail.rowIndex) + 1)}</strong></div>
      <div class="anomaly-detail-item"><span>Actual value</span><strong>${fmt(topDetail.actualValue)}</strong></div>
      <div class="anomaly-detail-item"><span>Expected range</span><strong>${escHtml(topDetail.expectedRange)}</strong></div>
      <div class="anomaly-detail-item"><span>Impact</span><strong>${escHtml(topDetail.impact || topDetail.deviation)}</strong></div>
      <div class="anomaly-detail-item"><span>Surrounding average</span><strong>${fmt(topDetail.surroundingAverage)}</strong></div>
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

  if (!columnName || !window.smartDetailedAnalysis) return;

  const analysis = window.smartDetailedAnalysis.find(a => a.column === columnName);
  if (analysis) {
    displayColumnAnalysis(analysis);
  }
}
