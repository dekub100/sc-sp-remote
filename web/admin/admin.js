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
    if (!res.ok) {
      showConfigStatus('Error loading config: HTTP ' + res.status, 'error');
      return;
    }
    const cfg = await res.json();
    document.getElementById('cfg-port').value = cfg.port;
    document.getElementById('cfg-origins').value = (cfg.allowedOrigins || []).join(', ');
    document.getElementById('cfg-volume').value = cfg.defaultVolume;
    document.getElementById('cfg-obs').checked = !!cfg.enableOBS;
    document.getElementById('cfg-website').checked = !!cfg.enableWebsite;
    document.getElementById('cfg-log-level').value = cfg.logLevel;
    document.getElementById('cfg-backup').value = cfg.backupCount;

    document.getElementById('cfg-progress-broadcast').value = cfg.progressBroadcastInterval;
    document.getElementById('cfg-save-debounce').value = cfg.stateSaveDebounceSeconds;
    document.getElementById('cfg-lyrics').checked = !!cfg.enableLyrics;
    document.getElementById('cfg-lyrics-timeout').value = cfg.lyricsFetchTimeoutSeconds;
    document.getElementById('cfg-provider-order').value = (cfg.lyricsProviderOrder || []).join(', ');

    document.getElementById('cfg-polling').value = cfg.spicetifyPollingIntervalMs;
    document.getElementById('cfg-reconnect-base').value = cfg.spicetifyReconnectBaseDelayMs;
    document.getElementById('cfg-reconnect-max').value = cfg.spicetifyReconnectMaxDelayMs;
    document.getElementById('cfg-progress-delta').value = cfg.spicetifyProgressDeltaThresholdMs;
    document.getElementById('cfg-command-feedback').value = cfg.spicetifyCommandFeedbackDelayMs;

    document.getElementById('cfg-up-next').value = cfg.obsUpNextThresholdMs;
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
    enableOBS: document.getElementById('cfg-obs').checked,
    enableWebsite: document.getElementById('cfg-website').checked,
    enableLyrics: document.getElementById('cfg-lyrics').checked,
    logLevel: document.getElementById('cfg-log-level').value,
    backupCount: parseInt(document.getElementById('cfg-backup').value),
    progressBroadcastInterval: parseFloat(document.getElementById('cfg-progress-broadcast').value),
    stateSaveDebounceSeconds: parseFloat(document.getElementById('cfg-save-debounce').value),
    lyricsFetchTimeoutSeconds: parseInt(document.getElementById('cfg-lyrics-timeout').value),
    lyricsProviderOrder: document.getElementById('cfg-provider-order').value.split(',').map(s => s.trim()).filter(Boolean),
    spicetifyPollingIntervalMs: parseInt(document.getElementById('cfg-polling').value),
    spicetifyReconnectBaseDelayMs: parseInt(document.getElementById('cfg-reconnect-base').value),
    spicetifyReconnectMaxDelayMs: parseInt(document.getElementById('cfg-reconnect-max').value),
    spicetifyProgressDeltaThresholdMs: parseInt(document.getElementById('cfg-progress-delta').value),
    spicetifyCommandFeedbackDelayMs: parseInt(document.getElementById('cfg-command-feedback').value),
    obsUpNextThresholdMs: parseInt(document.getElementById('cfg-up-next').value),
  };

  try {
    const res = await fetch(`${API}/api/admin/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      showConfigStatus('~~ Config saved!! Reconnect clients to apply. ~~', 'success');
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
    if (!res.ok) {
      ui.logList.innerHTML = '<p class="error">Error loading logs: HTTP ' + res.status + '</p>';
      return;
    }
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

document.getElementById('mxm-token-btn').addEventListener('click', async (e) => {
  const btn = e.target;
  btn.disabled = true;
  btn.value = '  ~~ Refreshing... ~~  ';
  try {
    const res = await fetch(`${API}/api/admin/lyrics/musixmatch-token`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showConfigStatus('~~ Musixmatch token refreshed (' + data.tokenPreview + ') ~~', 'success');
    } else {
      showConfigStatus('Error: ' + (data.error || 'Token refresh failed'), 'error');
    }
  } catch (e) {
    showConfigStatus('Error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.value = '  ~~ Refresh Token ~~  ';
  }
});

loadConfig();
