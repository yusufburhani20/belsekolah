from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import logging
import yt_dlp
from werkzeug.utils import secure_filename

from config import DATABASE_URI, SOUNDS_DIR, SECRET_KEY
from models import db, Jadwal, Profil, AudioFile, KalenderLibur, LogAktivitas, Pengaturan, User
from audio import audio_engine
from scheduler import init_scheduler, shutdown_scheduler

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ─── App Setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=SECRET_KEY,
    UPLOAD_FOLDER=SOUNDS_DIR,
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB
)

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'flac'}

db.init_app(app)

# ─── Jinja2 Filters ───────────────────────────────────────────────────────────
_HARI_NAMES = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']

@app.template_filter('hari_label')
def hari_label_filter(bitmask: int) -> str:
    days = [_HARI_NAMES[i] for i in range(7) if bitmask & (1 << i)]
    return ', '.join(days) if days else '—'

# ─── Init DB + Scheduler ──────────────────────────────────────────────────────
reload_jadwal = None

with app.app_context():
    db.create_all()
    if Profil.query.count() == 0:
        db.session.add_all([
            Profil(nama='Normal (Sen–Kam)'),
            Profil(nama='Jadwal Jumat'),
            Profil(nama='Jadwal Sabtu'),
        ])
        db.session.commit()
        logger.info("Default profil seeded")
    
    if AudioFile.query.count() == 0:
        sample_path = os.path.join(SOUNDS_DIR, 'bell_sample.wav')
        db.session.add(AudioFile(nama='Sample Bell', path=sample_path, tipe='lokal'))
        db.session.commit()
        logger.info("Default audio seeded")

    if User.query.count() == 0:
        admin_user = User(username='admin')
        admin_user.set_password('admin')
        db.session.add(admin_user)
        db.session.commit()
        logger.info("Default admin user seeded")

    # Restore volume from settings on startup
    try:
        vol = Pengaturan.get_val('volume', '80')
        audio_engine.set_volume(int(vol))
        logger.info(f"Volume system restored to {vol}% on startup")
    except Exception as e:
        logger.error(f"Failed to restore initial volume settings: {e}")

reload_jadwal = init_scheduler(app, db, audio_engine)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    from datetime import datetime, date
    today = date.today()
    today_bitmask = 1 << today.weekday()  # Mon=0 → bit 0

    jadwal_hari_ini = (
        Jadwal.query
        .filter(Jadwal.aktif == True, (Jadwal.hari.op('&')(today_bitmask)) > 0)
        .order_by(Jadwal.waktu)
        .all()
    )
    libur = KalenderLibur.query.filter_by(tanggal=today).first()
    log_terbaru = LogAktivitas.query.order_by(LogAktivitas.waktu.desc()).limit(15).all()
    audio_list = AudioFile.query.all()

    return render_template('dashboard.html',
        jadwal_hari_ini=jadwal_hari_ini,
        libur=libur,
        log_terbaru=log_terbaru,
        audio_list=audio_list,
        now=datetime.now(),
    )


@app.route('/jadwal')
def jadwal_page():
    return render_template('jadwal.html',
        jadwal_list=Jadwal.query.order_by(Jadwal.waktu).all(),
        audio_list=AudioFile.query.all(),
        profil_list=Profil.query.all(),
    )


@app.route('/audio')
def audio_page():
    return render_template('audio.html', audio_list=AudioFile.query.all())


@app.route('/pengaturan')
def pengaturan_page():
    return render_template('pengaturan.html',
        libur_list=KalenderLibur.query.order_by(KalenderLibur.tanggal).all(),
        profil_list=Profil.query.all(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API — SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/status')
def api_status():
    return jsonify({'playing': audio_engine.is_playing()})


@app.route('/api/test-bel', methods=['POST'])
def api_test_bel():
    data = request.get_json() or {}
    audio_id = data.get('audio_id')
    if audio_id:
        af = db.session.get(AudioFile, int(audio_id))
        if af:
            if af.tipe == 'youtube':
                audio_engine.play_youtube(af.path, 2)
            else:
                audio_engine.play_local(af.path, 2)
    log = LogAktivitas(aksi='Test Bel Manual', status='OK')
    db.session.add(log)
    db.session.commit()
    return jsonify({'status': 'ok', 'message': 'Bel dibunyikan'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    audio_engine.stop()
    return jsonify({'status': 'ok'})


@app.route('/api/volume', methods=['POST'])
def api_volume():
    data = request.get_json() or {}
    level = max(0, min(100, int(data.get('level', 80))))
    ok = audio_engine.set_volume(level)
    return jsonify({'status': 'ok' if ok else 'error', 'level': level})


# ═══════════════════════════════════════════════════════════════════════════════
# API — JADWAL
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/jadwal', methods=['GET', 'POST'])
def api_jadwal():
    if request.method == 'GET':
        return jsonify([j.to_dict() for j in Jadwal.query.order_by(Jadwal.waktu).all()])

    data = request.get_json() or {}
    try:
        jadwal = Jadwal(
            nama=data['nama'],
            waktu=data['waktu'],
            hari=int(data['hari']),
            audio_id=data.get('audio_id') or None,
            profil_id=data.get('profil_id') or None,
            durasi_menit=int(data.get('durasi_menit', 1)),
            aktif=bool(data.get('aktif', True)),
        )
        db.session.add(jadwal)
        db.session.commit()
        reload_jadwal()
        return jsonify({'status': 'ok', 'jadwal': jadwal.to_dict()})
    except KeyError as e:
        return jsonify({'status': 'error', 'message': f'Field wajib: {e}'}), 400


@app.route('/api/jadwal/<int:id>', methods=['PUT'])
def api_edit_jadwal(id):
    jadwal = db.session.get(Jadwal, id)
    if not jadwal:
        return jsonify({'status': 'error', 'message': 'Jadwal tidak ditemukan'}), 404
        
    data = request.get_json() or {}
    try:
        jadwal.nama = data.get('nama', jadwal.nama).strip()
        jadwal.waktu = data.get('waktu', jadwal.waktu)
        jadwal.hari = int(data.get('hari', jadwal.hari))
        jadwal.audio_id = data.get('audio_id') or None
        jadwal.durasi_menit = int(data.get('durasi_menit', jadwal.durasi_menit))
        
        db.session.commit()
        reload_jadwal()
        return jsonify({'status': 'ok', 'jadwal': jadwal.to_dict()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/jadwal/<int:id>', methods=['DELETE'])
def api_hapus_jadwal(id):
    jadwal = db.session.get(Jadwal, id)
    if not jadwal:
        return jsonify({'status': 'error'}), 404
    db.session.delete(jadwal)
    db.session.commit()
    reload_jadwal()
    return jsonify({'status': 'ok'})


@app.route('/api/jadwal/<int:id>/toggle', methods=['POST'])
def api_toggle_jadwal(id):
    jadwal = db.session.get(Jadwal, id)
    if not jadwal:
        return jsonify({'status': 'error'}), 404
    jadwal.aktif = not jadwal.aktif
    db.session.commit()
    reload_jadwal()
    return jsonify({'status': 'ok', 'aktif': jadwal.aktif})


# ═══════════════════════════════════════════════════════════════════════════════
# API — AUDIO
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/audio', methods=['GET'])
def api_audio_list():
    return jsonify([a.to_dict() for a in AudioFile.query.all()])


@app.route('/api/audio/upload', methods=['POST'])
def api_upload_audio():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file'}), 400
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'status': 'error', 'message': 'Format tidak didukung'}), 400
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(SOUNDS_DIR, filename)
    file.save(filepath)
    af = AudioFile(nama=filename, path=filepath, tipe='lokal')
    db.session.add(af)
    db.session.commit()
    return jsonify({'status': 'ok', 'audio': af.to_dict()})


@app.route('/api/audio/youtube', methods=['POST'])
def api_tambah_youtube():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'status': 'error', 'message': 'URL wajib diisi'}), 400
    af = AudioFile(nama=data.get('nama', 'YouTube Audio'), path=url, tipe='youtube')
    db.session.add(af)
    db.session.commit()
    return jsonify({'status': 'ok', 'audio': af.to_dict()})


@app.route('/api/audio/<int:id>', methods=['DELETE'])
def api_hapus_audio(id):
    af = db.session.get(AudioFile, id)
    if not af:
        return jsonify({'status': 'error'}), 404
    if af.tipe == 'lokal' and af.path and os.path.exists(af.path):
        os.remove(af.path)
    db.session.delete(af)
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/api/audio/<int:id>/play', methods=['POST'])
def api_play_audio(id):
    af = db.session.get(AudioFile, id)
    if not af:
        return jsonify({'status': 'error'}), 404
    if af.tipe == 'youtube':
        audio_engine.play_youtube(af.path)
    else:
        audio_engine.play_local(af.path)
    return jsonify({'status': 'ok'})


@app.route('/api/audio/play-raw', methods=['POST'])
def api_play_raw():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    tipe = data.get('tipe', 'youtube')
    if not url:
        return jsonify({'status': 'error', 'message': 'URL wajib diisi'}), 400
    if tipe == 'youtube':
        audio_engine.play_youtube(url)
    else:
        audio_engine.play_local(url)
    return jsonify({'status': 'ok'})


# ═══════════════════════════════════════════════════════════════════════════════
# API — YOUTUBE SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/youtube/search')
def api_youtube_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'ytsearch8:{query}', download=False)
            results = []
            for entry in (info.get('entries') or []):
                thumbs = entry.get('thumbnails') or []
                thumbnail = thumbs[-1].get('url') if thumbs else None
                results.append({
                    'title': entry.get('title', 'Unknown'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                    'duration': entry.get('duration'),
                    'thumbnail': thumbnail,
                    'channel': entry.get('uploader') or entry.get('channel') or '',
                })
            return jsonify({'results': results})
    except Exception as e:
        logger.error(f"YouTube search error: {e}")
        return jsonify({'results': [], 'error': str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# API — LIBUR
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/libur', methods=['POST'])
def api_tambah_libur():
    data = request.get_json() or {}
    from datetime import date
    try:
        libur = KalenderLibur(
            tanggal=date.fromisoformat(data['tanggal']),
            keterangan=data.get('keterangan', ''),
        )
        db.session.add(libur)
        db.session.commit()
        return jsonify({'status': 'ok', 'id': libur.id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/libur/<int:id>', methods=['DELETE'])
def api_hapus_libur(id):
    libur = db.session.get(KalenderLibur, id)
    if not libur:
        return jsonify({'status': 'error'}), 404
    db.session.delete(libur)
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/api/log')
def api_log():
    logs = LogAktivitas.query.order_by(LogAktivitas.waktu.desc()).limit(50).all()
    return jsonify([{
        'waktu': l.waktu.strftime('%Y-%m-%d %H:%M:%S'),
        'aksi': l.aksi,
        'status': l.status,
    } for l in logs])


# ═══════════════════════════════════════════════════════════════════════════════
# API — SETTINGS & NETWORK
# ═══════════════════════════════════════════════════════════════════════════════

# Audio devices scanner helper
def get_audio_devices():
    import subprocess
    devices = [{'id': 'default', 'name': 'Default Output Device'}]
    if os.name == 'nt':
        try:
            ps_cmd = "Get-CimInstance Win32_SoundDevice | Select-Object Name, DeviceID | ConvertTo-Json"
            res = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, text=True)
            if res.stdout.strip():
                import json
                win_devices = json.loads(res.stdout)
                if not isinstance(win_devices, list):
                    win_devices = [win_devices]
                for d in win_devices:
                    name = d.get('Name')
                    dev_id = d.get('DeviceID')
                    if name:
                        devices.append({'id': dev_id or name, 'name': name})
        except Exception as e:
            logger.error(f"Error listing Windows audio devices: {e}")
    else:
        try:
            res = subprocess.run(['aplay', '-L'], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.splitlines()
                current_id = None
                for line in lines:
                    if not line:
                        continue
                    if line.startswith(' ') or line.startswith('\t'):
                        if current_id and line.strip():
                            for d in devices:
                                if d['id'] == current_id:
                                    d['name'] = f"{line.strip()} ({current_id})"
                                    break
                            current_id = None
                    else:
                        device_id = line.strip()
                        if device_id and not any(device_id.startswith(p) for p in ['null', 'dmix', 'dsnoop', 'hw', 'plughw']):
                            devices.append({'id': device_id, 'name': device_id})
                            current_id = device_id
        except Exception as e:
            logger.error(f"Error listing Linux audio devices: {e}")
    return devices


# Network status helper
def get_network_status():
    import json
    import subprocess
    status = {
        'lan': {'status': 'disconnected', 'ip': None, 'conn': None},
        'wifi': {'status': 'disconnected', 'ip': None, 'conn': None, 'ssid': None}
    }
    
    if os.name == 'nt':
        try:
            # 1. Get adapter statuses (Up / Disconnected)
            adapter_status = {}
            ps_ad_cmd = "Get-NetAdapter | Select-Object Name, Status | ConvertTo-Json"
            res_ad = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_ad_cmd], capture_output=True, text=True)
            if res_ad.stdout.strip():
                try:
                    adapters_list = json.loads(res_ad.stdout)
                    if not isinstance(adapters_list, list):
                        adapters_list = [adapters_list]
                    for ad in adapters_list:
                        name = ad.get('Name', '')
                        status_str = ad.get('Status', '').lower()
                        adapter_status[name.lower()] = 'connected' if status_str == 'up' else 'disconnected'
                except Exception as je:
                    logger.error(f"JSON parse error for NetAdapter: {je}")

            # 2. Get IP addresses
            ps_ip_cmd = "Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress | ConvertTo-Json"
            res_ip = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_ip_cmd], capture_output=True, text=True)
            if res_ip.stdout.strip():
                try:
                    ips_list = json.loads(res_ip.stdout)
                    if not isinstance(ips_list, list):
                        ips_list = [ips_list]
                    for item in ips_list:
                        alias = item.get('InterfaceAlias', '')
                        alias_lower = alias.lower()
                        ip = item.get('IPAddress', '')
                        
                        # Skip IPv6, loopback, and APIPA autoconfigured IPs (169.254.x.x)
                        if '.' in ip and ip != '127.0.0.1' and not ip.startswith('169.254.'):
                            is_up = adapter_status.get(alias_lower, 'disconnected') == 'connected'
                            
                            # Filter out virtual environments
                            if 'virtualbox' in alias_lower or 'vEthernet' in alias_lower:
                                continue
                                
                            if 'wi-fi' in alias_lower or 'wifi' in alias_lower or 'wireless' in alias_lower:
                                status['wifi']['ip'] = ip
                                if is_up:
                                    status['wifi']['status'] = 'connected'
                            elif 'ethernet' in alias_lower or 'lan' in alias_lower or 'local area' in alias_lower:
                                if not status['lan']['ip'] or alias_lower == 'ethernet':
                                    status['lan']['ip'] = ip
                                    if is_up:
                                        status['lan']['status'] = 'connected'
                except Exception as je:
                    logger.error(f"JSON parse error for NetIPAddress: {je}")
            
            # 3. Get connected SSID
            wifi_ssid_cmd = "(netsh wlan show interfaces) | Select-String 'SSID' | ForEach-Object { $_.ToString().Split(':')[1].Trim() }"
            res_ssid = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', wifi_ssid_cmd], capture_output=True, text=True)
            lines = res_ssid.stdout.strip().splitlines()
            for line in lines:
                if line and not line.startswith('BSSID') and not line.startswith('SSID'):
                    status['wifi']['ssid'] = line.strip()
                    status['wifi']['status'] = 'connected'
                    break
        except Exception as e:
            logger.error(f"Error getting Windows network status: {e}")
    else:
        try:
            res = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'], capture_output=True, text=True)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    parts = line.split(':')
                    if len(parts) >= 4:
                        dev, dev_type, state, conn = parts[0], parts[1], parts[2], parts[3]
                        if dev_type == 'ethernet':
                            status['lan']['status'] = state
                            status['lan']['conn'] = conn if conn else None
                        elif dev_type == 'wifi':
                            status['wifi']['status'] = state
                            status['wifi']['conn'] = conn if conn else None
                            if state == 'connected' and conn:
                                status['wifi']['ssid'] = conn
            
            ip_res = subprocess.run(['ip', '-o', '-4', 'addr', 'list'], capture_output=True, text=True)
            if ip_res.returncode == 0:
                for line in ip_res.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 4:
                        iface = parts[1]
                        ip_with_subnet = parts[3]
                        ip = ip_with_subnet.split('/')[0]
                        if iface.startswith('eth') or iface.startswith('en'):
                            status['lan']['ip'] = ip
                            status['lan']['status'] = 'connected'
                        elif iface.startswith('wlan') or iface.startswith('wl'):
                            status['wifi']['ip'] = ip
                            status['wifi']['status'] = 'connected'
            if status['wifi']['conn'] == 'Hotspot':
                status['wifi']['status'] = 'disconnected'
                status['wifi']['ip'] = None
                status['wifi']['ssid'] = None
        except Exception as e:
            logger.error(f"Error getting Linux network status: {e}")
            
    return status


# Wi-Fi Scan helper
def scan_wifi():
    import subprocess
    networks = []
    if os.name == 'nt':
        try:
            cmd = "netsh wlan show networks | Select-String 'SSID' | ForEach-Object { $_.ToString().Split(':')[1].Trim() }"
            res = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd], capture_output=True, text=True)
            found = []
            for line in res.stdout.strip().splitlines():
                if line.strip():
                    found.append(line.strip())
            
            if found:
                for ssid in found:
                    networks.append({
                        'ssid': ssid,
                        'signal': 85,
                        'security': 'WPA2-Personal',
                        'active': False
                    })
            else:
                networks = [
                    {'ssid': 'Wifi_Sekolah_Utama', 'signal': 95, 'security': 'WPA2-Personal', 'active': False},
                    {'ssid': 'TU_Wifi', 'signal': 70, 'security': 'WPA2-Personal', 'active': False},
                    {'ssid': 'Guru_Hotspot', 'signal': 55, 'security': 'Open', 'active': False},
                    {'ssid': 'Lab_Komputer', 'signal': 40, 'security': 'WPA2-Enterprise', 'active': False}
                ]
        except Exception:
            networks = [
                {'ssid': 'Wifi_Sekolah_Utama (Mock)', 'signal': 95, 'security': 'WPA2-Personal', 'active': False}
            ]
    else:
        try:
            subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], capture_output=True)
            res = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,ACTIVE', 'device', 'wifi', 'list'], capture_output=True, text=True)
            if res.returncode == 0:
                seen_ssids = {}
                for line in res.stdout.strip().splitlines():
                    if not line:
                        continue
                    parts = line.split(':')
                    if len(parts) >= 4:
                        active = parts[-1].lower() == 'yes'
                        security = parts[-2]
                        signal_str = parts[-3]
                        ssid = ':'.join(parts[:-3])
                        
                        if not ssid:
                            continue
                            
                        try:
                            signal = int(signal_str)
                        except ValueError:
                            signal = 0
                            
                        if ssid not in seen_ssids or signal > seen_ssids[ssid]['signal']:
                            seen_ssids[ssid] = {
                                'ssid': ssid,
                                'signal': signal,
                                'security': security if security else 'Open',
                                'active': active
                            }
                networks = list(seen_ssids.values())
                networks.sort(key=lambda x: x['signal'], reverse=True)
        except Exception as e:
            logger.error(f"Error scanning Wi-Fi: {e}")
            
    return networks


# Wi-Fi Connect helper
def connect_wifi(ssid, password):
    import time
    import subprocess
    if os.name == 'nt':
        time.sleep(2)
        return True, "Koneksi simulasi berhasil di Windows"
    else:
        try:
            cmd = ['nmcli', 'device', 'wifi', 'connect', ssid]
            if password:
                cmd.extend(['password', password])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return True, "Berhasil terhubung ke Wi-Fi"
            else:
                err_msg = res.stderr.strip() or res.stdout.strip() or "Gagal terhubung"
                return False, err_msg
        except subprocess.TimeoutExpired:
            return False, "Koneksi ke Wi-Fi timeout"
        except Exception as e:
            return False, f"Error: {str(e)}"


# Wi-Fi Disconnect helper
def disconnect_wifi(ssid):
    if ssid == 'Hotspot' or ssid.lower() == 'bell':
        return False, "Tidak dapat memutuskan koneksi hotspot bawaan!"
    import subprocess
    if os.name == 'nt':
        return True, f"Koneksi ke '{ssid}' berhasil diputuskan (Simulasi)"
    try:
        subprocess.run(['nmcli', 'connection', 'modify', ssid, 'connection.autoconnect', 'no'], capture_output=True)
        res = subprocess.run(['nmcli', 'connection', 'down', 'id', ssid], capture_output=True, text=True)
        if res.returncode == 0:
            return True, f"Berhasil memutuskan koneksi dari '{ssid}'"
        else:
            err = res.stderr.strip() or res.stdout.strip() or "Gagal memutuskan"
            return False, err
    except Exception as e:
        return False, str(e)


# Wi-Fi Forget helper
def forget_wifi(ssid):
    if ssid == 'Hotspot' or ssid.lower() == 'bell':
        return False, "Tidak dapat menghapus profil hotspot bawaan!"
    import subprocess
    if os.name == 'nt':
        return True, f"Jaringan '{ssid}' berhasil dilupakan (Simulasi)"
    try:
        res = subprocess.run(['nmcli', 'connection', 'delete', 'id', ssid], capture_output=True, text=True)
        if res.returncode == 0:
            return True, f"Berhasil melupakan jaringan '{ssid}'"
        else:
            err = res.stderr.strip() or res.stdout.strip() or "Gagal melupakan jaringan"
            return False, err
    except Exception as e:
        return False, str(e)


def get_wifi_interface():
    import subprocess
    try:
        res = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,TYPE', 'device'], capture_output=True, text=True)
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = line.split(':')
                if len(parts) >= 2 and parts[1] == 'wifi':
                    return parts[0]
    except Exception:
        pass
    return 'wlan0'


def get_hotspot_status():
    import subprocess
    status = {
        'active': False,
        'ssid': 'bell',
        'password': 'admin123',
        'autoconnect': True
    }
    
    if os.name == 'nt':
        status['active'] = getattr(app, '_mock_hotspot_active', True)
        status['autoconnect'] = getattr(app, '_mock_hotspot_autoconnect', True)
        return status

    try:
        res_active = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'], capture_output=True, text=True)
        if res_active.returncode == 0:
            for line in res_active.stdout.strip().splitlines():
                parts = line.split(':')
                if len(parts) >= 2 and parts[0] == 'Hotspot':
                    status['active'] = True
                    break
                    
        res_details = subprocess.run(['nmcli', '-t', '-f', 'connection.id,connection.autoconnect,802-11-wireless.ssid,802-11-wireless-security.psk', 'connection', 'show', 'Hotspot'], capture_output=True, text=True)
        if res_details.returncode == 0:
            for line in res_details.stdout.strip().splitlines():
                if ':' in line:
                    key, val = line.split(':', 1)
                    if key == '802-11-wireless.ssid':
                        status['ssid'] = val
                    elif key == '802-11-wireless-security.psk':
                        status['password'] = val
                    elif key == 'connection.autoconnect':
                        status['autoconnect'] = (val.lower() == 'yes')
    except Exception as e:
        logger.error(f"Error getting Hotspot status: {e}")
        
    return status


def configure_hotspot(action, ssid='bell', password='admin123', autoconnect=True):
    import subprocess
    if os.name == 'nt':
        app._mock_hotspot_active = (action == 'enable')
        app._mock_hotspot_autoconnect = autoconnect
        return True, f"Hotspot {action}d successfully (Simulasi Windows)"

    if action == 'enable':
        ifname = get_wifi_interface()
        if not ifname:
            return False, "Tidak ditemukan interface Wi-Fi pada STB!"
            
        subprocess.run(['nmcli', 'connection', 'delete', 'Hotspot'], capture_output=True)
        
        cmd = ['nmcli', 'device', 'wifi', 'hotspot', 'ssid', ssid, 'password', password, 'ifname', ifname, 'con-name', 'Hotspot']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if res.returncode == 0:
            autoconnect_val = 'yes' if autoconnect else 'no'
            subprocess.run(['nmcli', 'connection', 'modify', 'Hotspot', 'connection.autoconnect', autoconnect_val], capture_output=True)
            return True, f"Hotspot berhasil diaktifkan dengan SSID '{ssid}'"
        else:
            err = res.stderr.strip() or res.stdout.strip() or "Error tidak diketahui"
            return False, f"Gagal mengaktifkan Hotspot: {err}"
            
    elif action == 'disable':
        res = subprocess.run(['nmcli', 'connection', 'down', 'Hotspot'], capture_output=True, text=True, timeout=15)
        subprocess.run(['nmcli', 'connection', 'modify', 'Hotspot', 'connection.autoconnect', 'no'], capture_output=True)
        
        if res.returncode == 0:
            return True, "Hotspot berhasil dinonaktifkan"
        else:
            status = get_hotspot_status()
            if not status['active']:
                return True, "Hotspot sudah tidak aktif"
            err = res.stderr.strip() or res.stdout.strip() or "Error tidak diketahui"
            return False, f"Gagal menonaktifkan Hotspot: {err}"


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        device = Pengaturan.get_val('audio_device', 'default')
        volume = Pengaturan.get_val('volume', '80')
        return jsonify({
            'audio_device': device,
            'volume': int(volume)
        })
    
    data = request.get_json() or {}
    try:
        if 'audio_device' in data:
            Pengaturan.set_val('audio_device', data['audio_device'])
        if 'volume' in data:
            level = max(0, min(100, int(data['volume'])))
            audio_engine.set_volume(level)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/audio-devices')
def api_audio_devices():
    devices = get_audio_devices()
    return jsonify({'devices': devices})


@app.route('/api/network/status')
def api_network_status():
    status = get_network_status()
    return jsonify(status)


@app.route('/api/network/wifi/scan')
def api_network_wifi_scan():
    networks = scan_wifi()
    return jsonify({'networks': networks})


@app.route('/api/network/wifi/connect', methods=['POST'])
def api_network_wifi_connect():
    data = request.get_json() or {}
    ssid = data.get('ssid', '').strip()
    password = data.get('password', '').strip()
    if not ssid:
        return jsonify({'status': 'error', 'message': 'SSID wajib diisi'}), 400
    
    success, msg = connect_wifi(ssid, password)
    if success:
        log = LogAktivitas(aksi=f"Connect Wi-Fi: {ssid}", status="OK")
        db.session.add(log)
        db.session.commit()
        return jsonify({'status': 'ok', 'message': msg})
    else:
        log = LogAktivitas(aksi=f"Gagal Connect Wi-Fi: {ssid}", status="ERROR")
        db.session.add(log)
        db.session.commit()
        return jsonify({'status': 'error', 'message': msg})


@app.route('/api/network/wifi/disconnect', methods=['POST'])
def api_network_wifi_disconnect():
    data = request.get_json() or {}
    ssid = data.get('ssid', '').strip()
    if not ssid:
        return jsonify({'status': 'error', 'message': 'SSID wajib diisi'}), 400
    
    success, msg = disconnect_wifi(ssid)
    log = LogAktivitas(
        aksi=f"Putuskan Wi-Fi: {ssid}", 
        status="OK" if success else "ERROR"
    )
    db.session.add(log)
    db.session.commit()
    
    if success:
        return jsonify({'status': 'ok', 'message': msg})
    else:
        return jsonify({'status': 'error', 'message': msg}), 500


@app.route('/api/network/wifi/forget', methods=['POST'])
def api_network_wifi_forget():
    data = request.get_json() or {}
    ssid = data.get('ssid', '').strip()
    if not ssid:
        return jsonify({'status': 'error', 'message': 'SSID wajib diisi'}), 400
    
    success, msg = forget_wifi(ssid)
    log = LogAktivitas(
        aksi=f"Lupakan Wi-Fi: {ssid}", 
        status="OK" if success else "ERROR"
    )
    db.session.add(log)
    db.session.commit()
    
    if success:
        return jsonify({'status': 'ok', 'message': msg})
    else:
        return jsonify({'status': 'error', 'message': msg}), 500


@app.route('/api/network/hotspot', methods=['GET', 'POST'])
def api_network_hotspot():
    if request.method == 'GET':
        return jsonify(get_hotspot_status())
        
    data = request.get_json() or {}
    action = data.get('action')
    ssid = data.get('ssid', 'bell').strip()
    password = data.get('password', 'admin123').strip()
    autoconnect = bool(data.get('autoconnect', True))
    
    if action not in ['enable', 'disable']:
        if 'autoconnect' in data:
            if os.name == 'nt':
                app._mock_hotspot_autoconnect = autoconnect
                return jsonify({'status': 'ok', 'message': 'Pengaturan disimpan (Simulasi)'})
            else:
                import subprocess
                val = 'yes' if autoconnect else 'no'
                res = subprocess.run(['nmcli', 'connection', 'modify', 'Hotspot', 'connection.autoconnect', val], capture_output=True)
                if res.returncode == 0:
                    return jsonify({'status': 'ok', 'message': 'Pengaturan autostart berhasil diubah'})
                else:
                    return jsonify({'status': 'error', 'message': 'Hotspot profile belum dikonfigurasi'}), 400
        return jsonify({'status': 'error', 'message': 'Parameter action wajib diisi (enable/disable)'}), 400
        
    if action == 'enable' and len(password) < 8:
        return jsonify({'status': 'error', 'message': 'Password hotspot minimal 8 karakter!'}), 400
        
    success, msg = configure_hotspot(action, ssid, password, autoconnect)
    
    log = LogAktivitas(
        aksi=f"{'Aktifkan' if action == 'enable' else 'Nonaktifkan'} Hotspot: {ssid}", 
        status="OK" if success else "ERROR"
    )
    db.session.add(log)
    db.session.commit()
    
    if success:
        return jsonify({'status': 'ok', 'message': msg})
    else:
        return jsonify({'status': 'error', 'message': msg}), 500


# ─── Authentication Proteksi ──────────────────────────────────────────────────
@app.before_request
def require_login():
    # Endpoints that do not require login
    allowed_endpoints = ['login', 'serve_sound', 'static']
    if request.endpoint in allowed_endpoints:
        return
    
    # Exclude path prefixes
    for prefix in ['/login', '/static', '/sounds']:
        if request.path.startswith(prefix):
            return
            
    if 'user_id' not in session:
        # If it's an API request, return JSON error instead of redirecting
        if request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': 'Authentication required'}), 401
        return redirect(url_for('login'))


# ─── Authentication Routes ────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            if request.is_json:
                return jsonify({'status': 'ok'})
            return redirect(url_for('dashboard'))
        else:
            msg = 'Username atau password salah!'
            if request.is_json:
                return jsonify({'status': 'error', 'message': msg}), 401
            return render_template('login.html', error=msg)
            
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ═══════════════════════════════════════════════════════════════════════════════
# API — USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/users', methods=['GET', 'POST'])
def api_users():
    if request.method == 'GET':
        users = User.query.all()
        return jsonify([u.to_dict() for u in users])
        
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username dan password wajib diisi'}), 400
        
    if User.query.filter_by(username=username).first():
        return jsonify({'status': 'error', 'message': f'Username "{username}" sudah terdaftar'}), 400
        
    try:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        log = LogAktivitas(aksi=f"Tambah User: {username}", status="OK")
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'status': 'ok', 'user': new_user.to_dict()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/users/<int:id>', methods=['PUT'])
def api_edit_user(id):
    user = db.session.get(User, id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User tidak ditemukan'}), 404
        
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username:
        return jsonify({'status': 'error', 'message': 'Username tidak boleh kosong'}), 400
        
    existing = User.query.filter(User.username == username, User.id != id).first()
    if existing:
        return jsonify({'status': 'error', 'message': f'Username "{username}" sudah terdaftar'}), 400
        
    try:
        user.username = username
        if password:
            user.set_password(password)
        db.session.commit()
        
        if user.id == session.get('user_id'):
            session['username'] = username
            
        log = LogAktivitas(aksi=f"Edit User: {username}", status="OK")
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'status': 'ok', 'user': user.to_dict()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/users/<int:id>', methods=['DELETE'])
def api_delete_user(id):
    user = db.session.get(User, id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User tidak ditemukan'}), 404
        
    if user.id == session.get('user_id'):
        return jsonify({'status': 'error', 'message': 'Tidak dapat menghapus akun yang sedang digunakan'}), 400
        
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        log = LogAktivitas(aksi=f"Hapus User: {username}", status="OK")
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─── Serve uploaded sounds ────────────────────────────────────────────────────
@app.route('/sounds/<path:filename>')
def serve_sound(filename):
    return send_from_directory(SOUNDS_DIR, filename)


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    finally:
        shutdown_scheduler()
