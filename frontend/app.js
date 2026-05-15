/* ══════════════════════════════════════
   DataLens — Frontend Application Logic
   ══════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────────
let token = localStorage.getItem('dl_token') || null;
let currentUser = JSON.parse(localStorage.getItem('dl_user') || 'null');
let connInfo = null;          // DB connection details
let availableTables = [];
let selectedTable = null;
let analyticsData = null;
let charts = {};              // Chart.js instances

// ── Init ───────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  if (token && currentUser) {
    showApp();
  } else {
    showAuth();
  }
});

function showAuth() {
  document.getElementById('authScreen').classList.remove('d-none');
  document.getElementById('appScreen').classList.add('d-none');
}
function showApp() {
  document.getElementById('authScreen').classList.add('d-none');
  document.getElementById('appScreen').classList.remove('d-none');
  document.getElementById('appScreen').style.display = 'flex';
  populateUserInfo();
}

function populateUserInfo() {
  if (!currentUser) return;
  const initial = (currentUser.name || 'U')[0].toUpperCase();
  document.getElementById('userAvatar').textContent = initial;
  document.getElementById('sidebarUserName').textContent = currentUser.name || 'User';
  document.getElementById('sidebarUserRole').textContent = currentUser.role || 'analyst';
}

// ── Auth Tab Switch ────────────────────────────────────────────────────
function switchTab(tab) {
  document.getElementById('loginForm').classList.toggle('d-none', tab !== 'login');
  document.getElementById('registerForm').classList.toggle('d-none', tab !== 'register');
  document.getElementById('tabLogin').classList.toggle('active', tab === 'login');
  document.getElementById('tabRegister').classList.toggle('active', tab === 'register');
}

// ── Register ───────────────────────────────────────────────────────────
async function doRegister() {
  const name     = document.getElementById('regName').value.trim();
  const email    = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  const errEl    = document.getElementById('registerError');

  hideEl(errEl);
  if (!name || !email || !password) return showError(errEl, 'All fields are required.');

  try {
    const res = await post('/api/auth/register', { name, email, password });
    if (res.error) return showError(errEl, res.error);
    saveSession(res);
    showApp();
  } catch (e) {
    showError(errEl, 'Network error. Is the server running?');
  }
}

// ── Login ──────────────────────────────────────────────────────────────
async function doLogin() {
  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl    = document.getElementById('loginError');

  hideEl(errEl);
  if (!email || !password) return showError(errEl, 'Email and password are required.');

  try {
    const res = await post('/api/auth/login', { email, password });
    if (res.error) return showError(errEl, res.error);
    saveSession(res);
    showApp();
  } catch (e) {
    showError(errEl, 'Network error. Is the server running?');
  }
}

function saveSession(res) {
  token = res.token;
  currentUser = res.user;
  localStorage.setItem('dl_token', token);
  localStorage.setItem('dl_user', JSON.stringify(currentUser));
}

function doLogout() {
  token = null;
  currentUser = null;
  connInfo = null;
  availableTables = [];
  selectedTable = null;
  analyticsData = null;
  localStorage.removeItem('dl_token');
  localStorage.removeItem('dl_user');
  showAuth();
}

// ── Navigation ─────────────────────────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const panelMap = { connect: 'panelConnect', dashboard: 'panelDashboard', data: 'panelData' };
  const titleMap = { connect: 'Connect to Database', dashboard: 'Analytics Dashboard', data: 'Data Preview' };

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
  if (!server || !database || !username) return showError(errEl, 'Server, database, and username are required.');

  const btn = document.getElementById('btnConnect');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;margin:0 auto"></div>';

  connInfo = { server, port, database, username, password, encrypt, trustCert };

  try {
    const res = await authPost('/api/db/connect', connInfo);
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';

    if (res.error) return showError(errEl, res.error);

    availableTables = res.tables;
    showSuccess(sucEl, `✓ Connected to "${res.database}" — ${res.tableCount} table(s) available`);

    // Show DB badge in topbar
    const badge = document.getElementById('dbBadge');
    badge.classList.remove('d-none');
    document.getElementById('dbBadgeText').textContent = `${res.database} (${res.tableCount} tables)`;

    renderTableList(res.tables);
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i><span>Connect & Fetch Tables</span>';
    showError(errEl, 'Network error. Is the server running?');
  }
}

function renderTableList(tables) {
  const card = document.getElementById('tableListCard');
  const list = document.getElementById('tableList');
  const badge = document.getElementById('tableCountBadge');

  badge.textContent = tables.length;
  list.innerHTML = '';

  if (tables.length === 0) {
    list.innerHTML = '<p style="color:var(--text-muted);font-size:12px;padding:8px">No accessible tables found.</p>';
  } else {
    tables.forEach(t => {
      const item = document.createElement('div');
      item.className = 'table-item';
      item.innerHTML = `<i class="bi bi-table"></i> ${escHtml(t)}`;
      item.addEventListener('click', () => selectTable(t, item));
      list.appendChild(item);
    });
  }

  card.style.display = 'block';
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

  content.classList.add('d-none');
  empty.classList.add('d-none');
  loading.classList.remove('d-none');
  document.getElementById('dashTableName').textContent = `Table: ${tableName}`;

  try {
    const res = await authPost('/api/analytics/table', { connInfo, tableName });
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

  const accentList = ['var(--accent)', 'var(--accent2)', 'var(--accent3)', 'var(--accent4)'];

  const cards = [
    { label: 'Total Rows', value: data.totalRows.toLocaleString(), sub: 'records in table', icon: 'bi-database', accent: accentList[0] },
    { label: 'Columns', value: data.columns.length, sub: 'fields detected', icon: 'bi-layout-three-columns', accent: accentList[1] },
    { label: 'Numeric Cols', value: data.numericStats.length, sub: 'measurable fields', icon: 'bi-123', accent: accentList[2] },
    { label: 'Sample Size', value: data.sampleRows.length, sub: 'rows previewed', icon: 'bi-eye', accent: accentList[3] }
  ];

  cards.forEach(c => {
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.style.setProperty('--card-accent', c.accent);
    card.innerHTML = `
      <div class="stat-label">${c.label}</div>
      <div class="stat-value">${c.value}</div>
      <div class="stat-sub">${c.sub}</div>
      <i class="bi ${c.icon} stat-icon"></i>
    `;
    row.appendChild(card);
  });

  // Extra stats from first numeric column
  if (data.numericStats.length > 0) {
    const ns = data.numericStats[0];
    [
      { label: `MIN — ${ns.column}`, value: fmt(ns.min), sub: 'minimum value', icon: 'bi-arrow-down-circle', accent: accentList[1] },
      { label: `MAX — ${ns.column}`, value: fmt(ns.max), sub: 'maximum value', icon: 'bi-arrow-up-circle', accent: accentList[0] },
      { label: `AVG — ${ns.column}`, value: fmt(ns.avg), sub: 'average value', icon: 'bi-calculator', accent: accentList[3] }
    ].forEach(c => {
      const card = document.createElement('div');
      card.className = 'stat-card';
      card.style.setProperty('--card-accent', c.accent);
      card.innerHTML = `
        <div class="stat-label">${c.label}</div>
        <div class="stat-value">${c.value}</div>
        <div class="stat-sub">${c.sub}</div>
        <i class="bi ${c.icon} stat-icon"></i>
      `;
      row.appendChild(card);
    });
  }
}

function renderCharts(data) {
  // Destroy old charts
  Object.values(charts).forEach(c => c.destroy());
  charts = {};

  const grid = document.getElementById('chartsGrid');
  grid.innerHTML = '';

  const chartDefaults = {
    plugins: {
      legend: { labels: { color: '#8892a4', font: { family: 'DM Mono', size: 11 } } }
    },
    scales: {
      x: { ticks: { color: '#8892a4', font: { family: 'DM Mono', size: 10 } }, grid: { color: '#252a38' } },
      y: { ticks: { color: '#8892a4', font: { family: 'DM Mono', size: 10 } }, grid: { color: '#252a38' } }
    }
  };

  // 1. Bar chart — numeric stats (min/max/avg)
  if (data.numericStats.length > 0) {
    const card = makeChartCard('Numeric Column Stats — Min / Avg / Max');
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    charts['numStats'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.numericStats.map(n => n.column),
        datasets: [
          { label: 'Min', data: data.numericStats.map(n => n.min), backgroundColor: '#4d9fff44', borderColor: '#4d9fff', borderWidth: 1.5 },
          { label: 'Avg', data: data.numericStats.map(n => n.avg), backgroundColor: '#00e5a044', borderColor: '#00e5a0', borderWidth: 1.5 },
          { label: 'Max', data: data.numericStats.map(n => n.max), backgroundColor: '#ffd16644', borderColor: '#ffd166', borderWidth: 1.5 }
        ]
      },
      options: { ...chartDefaults, responsive: true }
    });
  }

  // 2. Pie chart — category distribution
  if (data.categoryData && data.categoryData.data.length > 0) {
    const cat = data.categoryData;
    const card = makeChartCard(`Distribution — ${cat.column}`);
    grid.appendChild(card);
    const ctx = card.querySelector('canvas').getContext('2d');
    const colors = ['#00e5a0','#4d9fff','#ffd166','#ff6b6b','#c77dff','#06d6a0','#ef476f','#ffd166','#118ab2','#073b4c'];
    charts['category'] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cat.data.map(d => String(d.label).slice(0, 20)),
        datasets: [{ data: cat.data.map(d => d.count), backgroundColor: colors, borderColor: '#111318', borderWidth: 2 }]
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

// ── Helpers ────────────────────────────────────────────────────────────
async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return res.json();
}

async function authPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
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
  if (n === null || n === undefined) return '—';
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return Number(n).toLocaleString();
}
