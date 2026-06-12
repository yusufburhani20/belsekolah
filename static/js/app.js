/* ═══════════════════════════════════════════════════════════════════════════
   Bell Sekolah — app.js
   Global utilities, live clock, API helpers, UI interactions
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Live Clock ──────────────────────────────────────────────────────────────
(function initClock() {
  const clockEl = document.getElementById('liveClock');
  const dateEl  = document.getElementById('liveDate');
  if (!clockEl) return;

  const DAYS_ID = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'];
  const MONTHS_ID = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];

  function tick() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2,'0');
    const mm = String(now.getMinutes()).padStart(2,'0');
    const ss = String(now.getSeconds()).padStart(2,'0');
    clockEl.textContent = `${hh}:${mm}:${ss}`;
    if (dateEl) {
      const dayName = DAYS_ID[now.getDay()];
      const d = now.getDate();
      const mon = MONTHS_ID[now.getMonth()];
      const yr = now.getFullYear();
      dateEl.textContent = `${dayName}, ${d} ${mon} ${yr}`;
    }
    // Highlight next bell
    updateNextBell(now);
  }
  tick();
  setInterval(tick, 1000);
})();

// ─── Next Bell Calculator ────────────────────────────────────────────────────
function updateNextBell(now) {
  const el = document.getElementById('nextBellTime');
  if (!el) return;

  const times = window.jadwalHariIni || [];
  const hhmm = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
  const upcoming = times.filter(t => t > hhmm);
  el.textContent = upcoming.length > 0 ? upcoming[0] : '—';
}

// ─── Status Polling (every 5s) ───────────────────────────────────────────────
(function pollStatus() {
  const dot  = document.getElementById('statusDot');
  const txt  = document.getElementById('statusText');
  const play = document.getElementById('playingStatus');
  const brand = document.querySelector('.brand-icon');

  async function check() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (data.playing) {
        dot?.classList.add('playing');
        if (txt) txt.textContent = 'Sedang Memutar';
        if (play) play.textContent = 'Bermain 🎵';
        brand?.classList.add('ringing');
      } else {
        dot?.classList.remove('playing');
        if (txt) txt.textContent = 'Sistem Aktif';
        if (play) play.textContent = 'Idle';
        brand?.classList.remove('ringing');
      }
    } catch (_) {}
  }
  check();
  setInterval(check, 5000);
})();

// ─── Toast ───────────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg, type = 'info') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast ${type} show`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.classList.remove('show'); }, 3000);
}

// ─── API Helper ──────────────────────────────────────────────────────────────
async function api(method, url, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

// ─── Volume Slider ───────────────────────────────────────────────────────────
(function initVolume() {
  const slider = document.getElementById('volumeSlider');
  const valEl  = document.getElementById('volumeValue');
  if (!slider) return;

  let debounceTimer;
  slider.addEventListener('input', () => {
    if (valEl) valEl.textContent = `${slider.value}%`;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      await api('POST', '/api/volume', { level: parseInt(slider.value) });
    }, 400);
  });
})();

// ─── Stop Audio ──────────────────────────────────────────────────────────────
async function stopAudio() {
  await api('POST', '/api/stop');
  showToast('Audio dihentikan', 'info');
}

// ─── Test Bel ────────────────────────────────────────────────────────────────
async function testBel(audioId = null) {
  await api('POST', '/api/test-bel', { audio_id: audioId });
  showToast('🔔 Bel dibunyikan!', 'success');
  // Trigger bell shake
  const brand = document.querySelector('.brand-icon');
  if (brand) {
    brand.classList.add('ringing');
    setTimeout(() => brand.classList.remove('ringing'), 1000);
  }
}

// ─── Modal ───────────────────────────────────────────────────────────────────
function showModal(id) {
  document.getElementById(id)?.classList.add('open');
}
function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}
// Close on ESC
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open'));
  }
});

// ─── Day Selector Helper ─────────────────────────────────────────────────────
function getSelectedDays() {
  const checks = document.querySelectorAll('input[name="hari"]:checked');
  return Array.from(checks).reduce((sum, c) => sum + parseInt(c.value), 0);
}

// ─── Jadwal Form ─────────────────────────────────────────────────────────────
const formTambahJadwal = document.getElementById('formTambahJadwal');
if (formTambahJadwal) {
  formTambahJadwal.addEventListener('submit', async (e) => {
    e.preventDefault();
    const hari = getSelectedDays();
    if (!hari) {
      showToast('Pilih minimal satu hari!', 'error');
      return;
    }
    const data = {
      nama: document.getElementById('jNama').value.trim(),
      waktu: document.getElementById('jWaktu').value,
      hari,
      audio_id: parseInt(document.getElementById('jAudio').value) || null,
      durasi_menit: parseInt(document.getElementById('jDurasi').value) || 1,
      aktif: true,
    };
    const res = await api('POST', '/api/jadwal', data);
    if (res.status === 'ok') {
      showToast('Jadwal berhasil ditambahkan!', 'success');
      closeModal('modalTambahJadwal');
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(res.message || 'Gagal menyimpan jadwal', 'error');
    }
  });
}

// Double-click delete confirmation mapping
let deleteTimeouts = {};

async function hapusJadwal(id, btnElement) {
  if (!btnElement) {
    if (!confirm('Hapus jadwal ini?')) return;
    performDeleteJadwal(id);
    return;
  }
  if (btnElement.dataset.confirming === "true") {
    clearTimeout(deleteTimeouts['j_' + id]);
    performDeleteJadwal(id);
  } else {
    btnElement.dataset.confirming = "true";
    btnElement.innerHTML = "⚠️ Yakin?";
    btnElement.style.width = "auto";
    btnElement.style.padding = "0 8px";
    btnElement.style.fontSize = "0.75rem";
    deleteTimeouts['j_' + id] = setTimeout(() => {
      btnElement.dataset.confirming = "false";
      btnElement.innerHTML = "🗑";
      btnElement.style.width = "";
      btnElement.style.padding = "";
      btnElement.style.fontSize = "";
    }, 3000);
  }
}

async function performDeleteJadwal(id) {
  try {
    const res = await api('DELETE', `/api/jadwal/${id}`);
    if (res.status === 'ok') {
      showToast('✅ Jadwal berhasil dihapus!', 'success');
      document.querySelector(`#jadwal-row-${id}`)?.remove();
      setTimeout(() => location.reload(), 500);
    } else {
      showToast(res.message || 'Gagal menghapus jadwal', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function toggleJadwal(id, checkbox) {
  const res = await api('POST', `/api/jadwal/${id}/toggle`);
  if (res.status !== 'ok') {
    checkbox.checked = !checkbox.checked; // revert
    showToast('Gagal mengubah status', 'error');
  } else {
    showToast(res.aktif ? 'Jadwal diaktifkan' : 'Jadwal dinonaktifkan', 'info');
  }
}

async function testJadwal(jadwalId, audioId) {
  await testBel(audioId);
}

// ─── Audio Preview ───────────────────────────────────────────────────────────
async function previewAudio(id) {
  await api('POST', `/api/audio/${id}/play`);
  showToast('🎵 Memutar audio...', 'info');
}

async function hapusAudio(id, btnElement) {
  if (!btnElement) {
    if (!confirm('Hapus audio ini?')) return;
    performDeleteAudio(id);
    return;
  }
  if (btnElement.dataset.confirming === "true") {
    clearTimeout(deleteTimeouts['a_' + id]);
    performDeleteAudio(id);
  } else {
    btnElement.dataset.confirming = "true";
    btnElement.innerHTML = "⚠️ Yakin?";
    btnElement.style.width = "auto";
    btnElement.style.padding = "0 8px";
    btnElement.style.fontSize = "0.75rem";
    deleteTimeouts['a_' + id] = setTimeout(() => {
      btnElement.dataset.confirming = "false";
      btnElement.innerHTML = "🗑";
      btnElement.style.width = "";
      btnElement.style.padding = "";
      btnElement.style.fontSize = "";
    }, 3000);
  }
}

async function performDeleteAudio(id) {
  try {
    const res = await api('DELETE', `/api/audio/${id}`);
    if (res.status === 'ok') {
      showToast('✅ Audio berhasil dihapus!', 'success');
      document.getElementById(`audio-${id}`)?.remove();
    } else {
      showToast(res.message || 'Gagal menghapus audio', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ─── Tab Switcher ────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
  event.target.classList.add('active');
  document.getElementById(`tab${name.charAt(0).toUpperCase() + name.slice(1)}`)?.classList.remove('hidden');
}

// ─── File Upload (drag & drop) ───────────────────────────────────────────────
(function initUpload() {
  const zone    = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    uploadFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => uploadFiles(fileInput.files));
})();

async function uploadFiles(files) {
  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/audio/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.status === 'ok') {
        showToast(`✅ ${data.audio.nama} berhasil diupload`, 'success');
        appendAudioCard(data.audio, 'audioLokalGrid');
      } else {
        showToast(data.message || 'Upload gagal', 'error');
      }
    } catch (e) {
      showToast('Upload error: ' + e.message, 'error');
    }
  }
}

function appendAudioCard(audio, gridId) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  // Remove "empty" placeholder if exists
  grid.querySelector('.empty-state')?.remove();
  const icon = audio.tipe === 'youtube' ? '▶' : '🔔';
  const div = document.createElement('div');
  div.className = 'audio-card';
  div.id = `audio-${audio.id}`;
  div.innerHTML = `
    <div class="audio-icon">${icon}</div>
    <div class="audio-info">
      <div class="audio-name">${audio.nama}</div>
      <div class="audio-type">${audio.tipe === 'youtube' ? 'YouTube' : 'Lokal'}</div>
    </div>
    <div class="audio-actions">
      <button class="btn-icon" onclick="previewAudio(${audio.id})">▶</button>
      <button class="btn-icon btn-danger" onclick="hapusAudio(${audio.id})">🗑</button>
    </div>
  `;
  grid.appendChild(div);
}

// ─── YouTube Search ──────────────────────────────────────────────────────────
async function cariYoutube() {
  const q = document.getElementById('ytSearch')?.value.trim();
  if (!q) return;

  const results = document.getElementById('ytResults');
  results.innerHTML = '<div class="yt-loading"><div class="spinner"></div> Mencari...</div>';

  try {
    const res = await fetch(`/api/youtube/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    if (!data.results.length) {
      results.innerHTML = '<div class="yt-loading">Tidak ada hasil.</div>';
      return;
    }

    results.innerHTML = data.results.map(r => `
      <div class="yt-result">
        ${r.thumbnail ? `<img class="yt-thumb" src="${r.thumbnail}" alt="" loading="lazy">` : '<div class="yt-thumb"></div>'}
        <div class="yt-info">
          <div class="yt-title">${r.title}</div>
          <div class="yt-meta">${r.channel}${r.duration ? ' · ' + fmtDur(r.duration) : ''}</div>
        </div>
        <div class="yt-actions">
          <button class="btn-icon" onclick="previewYT('${r.url}')" title="Preview">▶</button>
          <button class="btn btn-primary" style="padding:5px 10px;font-size:0.75rem;" onclick="simpanYT('${r.url}','${escHtml(r.title)}')">+ Simpan</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    results.innerHTML = `<div class="yt-loading">Error: ${e.message}</div>`;
  }
}

async function tambahYoutubeUrl() {
  const url = document.getElementById('ytUrl')?.value.trim();
  if (!url || !url.startsWith('http')) {
    showToast('Masukkan URL YouTube yang valid', 'error');
    return;
  }
  await simpanYT(url, url);
}

async function simpanYT(url, nama) {
  const res = await api('POST', '/api/audio/youtube', { url, nama });
  if (res.status === 'ok') {
    showToast('✅ Audio YouTube disimpan!', 'success');
    appendAudioCard(res.audio, 'audioYoutubeGrid');
  } else {
    showToast(res.message || 'Gagal menyimpan', 'error');
  }
}

async function previewYT(url) {
  showToast('🎵 Menyiapkan streaming YouTube...', 'info');
  const res = await api('POST', '/api/audio/play-raw', { url, tipe: 'youtube' });
  if (res.status === 'ok') {
    showToast('🎵 Streaming YouTube aktif!', 'success');
  } else {
    showToast('Gagal memutar streaming', 'error');
  }
}

function fmtDur(sec) {
  if (!sec) return '';
  const m = Math.floor(sec / 60);
  const s = String(sec % 60).padStart(2, '0');
  return `${m}:${s}`;
}
function escHtml(str) {
  return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// YouTube search on Enter key
document.getElementById('ytSearch')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') cariYoutube();
});

// ─── Libur Form ───────────────────────────────────────────────────────────────
const formTambahLibur = document.getElementById('formTambahLibur');
if (formTambahLibur) {
  formTambahLibur.addEventListener('submit', async (e) => {
    e.preventDefault();
    const tanggal = document.getElementById('liburTanggal').value;
    const keterangan = document.getElementById('liburKet').value;
    if (!tanggal) { showToast('Pilih tanggal libur', 'error'); return; }
    const res = await api('POST', '/api/libur', { tanggal, keterangan });
    if (res.status === 'ok') {
      showToast('Hari libur ditambahkan', 'success');
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(res.message || 'Gagal', 'error');
    }
  });
}

async function hapusLibur(id) {
  if (!confirm('Hapus hari libur ini?')) return;
  const res = await api('DELETE', `/api/libur/${id}`);
  if (res.status === 'ok') {
    showToast('Hari libur dihapus', 'info');
    document.getElementById(`libur-${id}`)?.remove();
  }
}

// ─── Settings page & General settings sync ──────────────────────────────────
(async function initSettings() {
  const audioSelect = document.getElementById('settingAudioDevice');
  const slider = document.getElementById('volumeSlider');
  const valEl = document.getElementById('volumeValue');
  
  try {
    const settings = await api('GET', '/api/settings');
    
    if (slider && settings.volume !== undefined) {
      slider.value = settings.volume;
      if (valEl) valEl.textContent = `${settings.volume}%`;
    }
    
    if (audioSelect) {
      const devicesData = await api('GET', '/api/audio-devices');
      audioSelect.innerHTML = '';
      devicesData.devices.forEach(dev => {
        const opt = document.createElement('option');
        opt.value = dev.id;
        opt.textContent = dev.name;
        if (dev.id === settings.audio_device) {
          opt.selected = true;
        }
        audioSelect.appendChild(opt);
      });
      
      await loadNetworkStatus();
      await loadUsers();
    }
  } catch (err) {
    console.error("Settings sync error:", err);
  }
})();

async function saveAudioDeviceSetting() {
  const select = document.getElementById('settingAudioDevice');
  if (!select) return;
  
  const dev = select.value;
  const btn = document.getElementById('btnSaveAudioDevice');
  if (btn) btn.disabled = true;
  
  try {
    const res = await api('POST', '/api/settings', { audio_device: dev });
    if (res.status === 'ok') {
      showToast('✅ Audio output berhasil disimpan!', 'success');
    } else {
      showToast('Gagal menyimpan perangkat audio', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadNetworkStatus() {
  const lanIp = document.getElementById('lanIp');
  const lanBadge = document.getElementById('lanBadge');
  const wifiIp = document.getElementById('wifiIp');
  const wifiBadge = document.getElementById('wifiBadge');
  
  if (!lanIp) return;
  
  try {
    const status = await api('GET', '/api/network/status');
    
    if (status.lan.status === 'connected') {
      lanIp.textContent = status.lan.ip || 'Terhubung (IP tidak diketahui)';
      lanBadge.textContent = 'Online';
      lanBadge.className = 'net-badge connected';
    } else {
      lanIp.textContent = 'Kabel terputus / Tidak aktif';
      lanBadge.textContent = 'Offline';
      lanBadge.className = 'net-badge disconnected';
    }
    
    if (status.wifi.status === 'connected') {
      wifiIp.textContent = `${status.wifi.ip || 'Terhubung'} (${status.wifi.ssid || 'SSID tidak diketahui'})`;
      wifiBadge.textContent = 'Online';
      wifiBadge.className = 'net-badge connected';
    } else {
      wifiIp.textContent = 'Tidak terhubung';
      wifiBadge.textContent = 'Offline';
      wifiBadge.className = 'net-badge disconnected';
    }
  } catch (err) {
    console.error("Gagal memuat status jaringan:", err);
  }
}

async function scanWifiNetworks() {
  const container = document.getElementById('wifiListContainer');
  const btn = document.getElementById('btnScanWifi');
  if (!container) return;
  
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '🔄 Memindai...';
  }
  
  container.innerHTML = '<div class="wifi-loading"><div class="spinner"></div> Memindai jaringan Wi-Fi...</div>';
  
  try {
    const data = await api('GET', '/api/network/wifi/scan');
    
    if (!data.networks || data.networks.length === 0) {
      container.innerHTML = '<p class="empty-hint">Tidak ada jaringan Wi-Fi terdeteksi.</p>';
      return;
    }
    
    container.innerHTML = data.networks.map(net => {
      const isConnected = net.active;
      const signalClass = net.signal >= 75 ? 'sig-strong' : (net.signal >= 45 ? 'sig-medium' : 'sig-weak');
      const actionBtn = isConnected 
        ? `<span style="color:var(--text-success); font-weight:bold; font-size:0.85rem;">Terhubung ✅</span>`
        : `<button class="btn btn-primary" style="padding: 4px 10px; font-size:0.75rem;" onclick="promptConnectWifi('${escHtml(net.ssid)}')">Hubungkan</button>`;
      
      return `
        <div class="wifi-item">
          <div class="wifi-name-section">
            <span class="wifi-icon ${signalClass}">📶</span>
            <span class="wifi-ssid">${escHtml(net.ssid)}</span>
            <span style="font-size:0.7rem; color:var(--text-muted); margin-left:8px;">(${net.security})</span>
          </div>
          <div class="wifi-action-section">
            <span style="font-size:0.8rem; color:var(--text-muted); margin-right:12px;">${net.signal}%</span>
            ${actionBtn}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<p class="empty-hint" style="color:var(--text-danger);">Gagal memindai: ${err.message}</p>`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🔄 Pindai';
    }
  }
}

function promptConnectWifi(ssid) {
  const targetSsidEl = document.getElementById('wifiTargetSsid');
  const ssidInput = document.getElementById('wifiSsidInput');
  const passwordInput = document.getElementById('wifiPasswordInput');
  
  if (targetSsidEl) targetSsidEl.textContent = ssid;
  if (ssidInput) ssidInput.value = ssid;
  if (passwordInput) passwordInput.value = '';
  
  showModal('modalConnectWifi');
}

(function initConnectWifiForm() {
  const form = document.getElementById('formConnectWifi');
  if (!form) return;
  
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ssid = document.getElementById('wifiSsidInput').value;
    const password = document.getElementById('wifiPasswordInput').value;
    const btn = document.getElementById('btnWifiConnectSubmit');
    
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Menghubungkan...';
    }
    
    showToast(`Mencoba terhubung ke ${ssid}...`, 'info');
    
    try {
      const res = await api('POST', '/api/network/wifi/connect', { ssid, password });
      if (res.status === 'ok') {
        showToast(`✅ Berhasil: ${res.message}`, 'success');
        closeModal('modalConnectWifi');
        await loadNetworkStatus();
        await scanWifiNetworks();
      } else {
        showToast(`❌ Gagal: ${res.message}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Hubungkan';
      }
    }
  });
})();

// ─── User Management functions ──────────────────────────────────────────────
async function loadUsers() {
  const container = document.getElementById('userListContainer');
  if (!container) return;
  
  try {
    const users = await api('GET', '/api/users');
    
    if (!users || users.length === 0) {
      container.innerHTML = '<p class="empty-hint">Belum ada pengguna terdaftar.</p>';
      return;
    }
    
    container.innerHTML = users.map(u => {
      return `
        <div class="user-item" id="user-item-${u.id}" style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-input); border-radius:var(--radius-sm); margin-bottom:8px; border:1px solid var(--border);">
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:1.1rem;">👤</span>
            <span style="font-weight:600; font-size:0.875rem;">${escHtml(u.username)}</span>
            <span style="font-size:0.7rem; background:rgba(109,40,217,0.1); color:var(--accent-1); padding:2px 6px; border-radius:10px;">${escHtml(u.role)}</span>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn-icon" onclick="promptEditUser(${u.id}, '${escHtml(u.username)}')" title="Edit User">✏️</button>
            <button class="btn-icon btn-danger" onclick="hapusUser(${u.id}, this)" title="Hapus User">🗑</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<p class="empty-hint" style="color:var(--text-danger);">Gagal memuat: ${err.message}</p>`;
  }
}

function promptEditUser(id, username) {
  const idInput = document.getElementById('editUserIdInput');
  const usernameInput = document.getElementById('editUsername');
  const passwordInput = document.getElementById('editPassword');
  
  if (idInput) idInput.value = id;
  if (usernameInput) usernameInput.value = username;
  if (passwordInput) passwordInput.value = '';
  
  showModal('modalEditUser');
}

async function hapusUser(id, btnElement) {
  if (!btnElement) {
    if (!confirm('Hapus pengguna ini?')) return;
    performDeleteUser(id);
    return;
  }
  if (btnElement.dataset.confirming === "true") {
    clearTimeout(deleteTimeouts['u_' + id]);
    performDeleteUser(id);
  } else {
    btnElement.dataset.confirming = "true";
    btnElement.innerHTML = "⚠️ Yakin?";
    btnElement.style.width = "auto";
    btnElement.style.padding = "0 8px";
    btnElement.style.fontSize = "0.75rem";
    deleteTimeouts['u_' + id] = setTimeout(() => {
      btnElement.dataset.confirming = "false";
      btnElement.innerHTML = "🗑";
      btnElement.style.width = "";
      btnElement.style.padding = "";
      btnElement.style.fontSize = "";
    }, 3000);
  }
}

async function performDeleteUser(id) {
  try {
    const res = await api('DELETE', `/api/users/${id}`);
    if (res.status === 'ok') {
      showToast('✅ Pengguna berhasil dihapus!', 'success');
      document.getElementById(`user-item-${id}`)?.remove();
    } else {
      showToast(res.message || 'Gagal menghapus pengguna', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// Handler form tambah user
(function initTambahUserForm() {
  const form = document.getElementById('formTambahUser');
  if (!form) return;
  
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('newUsername').value.trim();
    const password = document.getElementById('newPassword').value;
    const btn = document.getElementById('btnTambahUserSubmit');
    
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Menyimpan...';
    }
    
    try {
      const res = await api('POST', '/api/users', { username, password });
      if (res.status === 'ok') {
        showToast('✅ Pengguna berhasil ditambahkan!', 'success');
        closeModal('modalTambahUser');
        await loadUsers();
      } else {
        showToast(`❌ Gagal: ${res.message}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Simpan';
      }
    }
  });
})();

// Handler form edit user
(function initEditUserForm() {
  const form = document.getElementById('formEditUser');
  if (!form) return;
  
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('editUserIdInput').value;
    const username = document.getElementById('editUsername').value.trim();
    const password = document.getElementById('editPassword').value;
    const btn = document.getElementById('btnEditUserSubmit');
    
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Menyimpan...';
    }
    
    try {
      const res = await api('PUT', `/api/users/${id}`, { username, password });
      if (res.status === 'ok') {
        showToast('✅ Pengguna berhasil diperbarui!', 'success');
        closeModal('modalEditUser');
        await loadUsers();
      } else {
        showToast(`❌ Gagal: ${res.message}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Error: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Simpan';
      }
    }
  });
})();

// ─── Sidebar Mobile Toggle ───────────────────────────────────────────────────
function toggleSidebar() {
  document.body.classList.toggle('sidebar-open');
}
