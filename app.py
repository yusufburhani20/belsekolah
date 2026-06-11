from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
import logging
import yt_dlp
from werkzeug.utils import secure_filename

from config import DATABASE_URI, SOUNDS_DIR, SECRET_KEY
from models import db, Jadwal, Profil, AudioFile, KalenderLibur, LogAktivitas
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

    return render_template('dashboard.html',
        jadwal_hari_ini=jadwal_hari_ini,
        libur=libur,
        log_terbaru=log_terbaru,
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
