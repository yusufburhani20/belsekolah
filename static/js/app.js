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
