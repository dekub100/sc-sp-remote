const API = window.location.origin;

const ui = {
  tabs: document.querySelectorAll('.nav-link[data-tab]'),
  tabContents: document.querySelectorAll('.tab-content'),
  configForm: document.getElementById('config-form'),
  configStatus: document.getElementById('config-status'),
  saveBtn: document.getElementById('save-btn'),
  logList: document.getElementById('log-list'),
  refreshLogsBtn: document.getElementById('refresh-logs-btn'),
  logViewer: document.getElementById('log-viewer'),
  logViewerTitle: document.getElementById('log-viewer-title'),
  logContent: document.getElementById('log-content'),
  closeLogBtn: document.getElementById('close-log-btn'),
};

function switchTab(name) {
  ui.tabs.forEach(b => {
    b.classList.toggle('nav-active', b.dataset.tab === name);
  });
  ui.tabContents.forEach(c => {
    c.classList.toggle('active', c.id === `${name}-tab`);
  });
  if (name === 'logs') loadLogs();
}

async function loadConfig() {
  try {
    const res = await fetch(`${API}/api/admin/config`);
    const cfg = await res.json();
    document.getElementById('cfg-port').value = cfg.port;
    document.getElementById('cfg-origins').value = (cfg.allowedOrigins || []).join(', ');
    document.getElementById('cfg-volume').value = cfg.defaultVolume;
    document.getElementById('cfg-volume-step').value = cfg.volumeStep;
    document.getElementById('cfg-max-queue').value = cfg.maxQueueSize;
    document.getElementById('cfg-rate-limit').value = cfg.queueRateLimitSeconds;
    document.getElementById('cfg-obs').checked = cfg.enableOBS;
    document.getElementById('cfg-website').checked = cfg.enableWebsite;
    document.getElementById('cfg-log-level').value = cfg.logLevel;
    document.getElementById('cfg-backup').value = cfg.backupCount;
    document.getElementById('info-port').textContent = cfg.port;
  } catch (e) {
    showConfigStatus('Error loading config: ' + e.message, 'error');
  }
}

function showConfigStatus(msg, type) {
  ui.configStatus.textContent = msg;
  ui.configStatus.className = type;
  setTimeout(() => { ui.configStatus.textContent = ''; ui.configStatus.className = ''; }, 4000);
}

async function saveConfig(e) {
  e.preventDefault();
  ui.saveBtn.disabled = true;
  ui.saveBtn.value = '  ~~ Saving... ~~  ';

  const payload = {
    port: parseInt(document.getElementById('cfg-port').value),
    allowedOrigins: document.getElementById('cfg-origins').value.split(',').map(s => s.trim()).filter(Boolean),
    defaultVolume: parseFloat(document.getElementById('cfg-volume').value),
    volumeStep: parseFloat(document.getElementById('cfg-volume-step').value),
    maxQueueSize: parseInt(document.getElementById('cfg-max-queue').value),
    queueRateLimitSeconds: parseInt(document.getElementById('cfg-rate-limit').value),
    enableOBS: document.getElementById('cfg-obs').checked,
    enableWebsite: document.getElementById('cfg-website').checked,
    logLevel: document.getElementById('cfg-log-level').value,
    backupCount: parseInt(document.getElementById('cfg-backup').value),
  };

  try {
    const res = await fetch(`${API}/api/admin/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      showConfigStatus('~~ Config saved successfully!! ~~', 'success');
    } else {
      showConfigStatus('Error: ' + (data.error || 'Save failed'), 'error');
    }
  } catch (e) {
    showConfigStatus('Error: ' + e.message, 'error');
  } finally {
    ui.saveBtn.disabled = false;
    ui.saveBtn.value = '  ~~ Save Config ~~  ';
  }
}

async function loadLogs() {
  try {
    const res = await fetch(`${API}/api/admin/logs`);
    const data = await res.json();
    renderLogList(data.logs || []);
  } catch (e) {
    ui.logList.innerHTML = '<p class="error">Error loading logs: ' + e.message + '</p>';
  }
}

function renderLogList(logs) {
  if (!logs.length) {
    ui.logList.innerHTML = '<p class="empty">No log files found :(</p>';
    return;
  }
  ui.logList.innerHTML = logs.map(log => {
    const date = new Date(log.modified * 1000);
    const size = log.size > 1024 ? (log.size / 1024).toFixed(1) + ' KB' : log.size + ' B';
    return '<div class="log-item" data-name="' + log.name + '">' +
      '<span class="log-name">' + log.name + '</span>' +
      '<span class="log-meta">' + size + ' | ' + date.toLocaleString() + '</span>' +
      '</div>';
  }).join('');

  ui.logList.querySelectorAll('.log-item').forEach(item => {
    item.addEventListener('click', () => openLog(item.dataset.name));
  });
}

async function openLog(filename) {
  ui.logViewerTitle.textContent = filename;
  ui.logContent.textContent = 'Loading...';
  ui.logViewer.classList.remove('hidden');

  try {
    const res = await fetch(`${API}/api/admin/logs/${encodeURIComponent(filename)}`);
    const text = await res.text();
    ui.logContent.textContent = text;
    ui.logContent.scrollTop = ui.logContent.scrollHeight;
  } catch (e) {
    ui.logContent.textContent = 'Error: ' + e.message;
  }
}

ui.refreshLogsBtn.addEventListener('click', loadLogs);
ui.closeLogBtn.addEventListener('click', () => ui.logViewer.classList.add('hidden'));
ui.configForm.addEventListener('submit', saveConfig);

loadConfig();
