from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Profil(db.Model):
    __tablename__ = 'profil'
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    aktif = db.Column(db.Boolean, default=True)
    jadwal = db.relationship('Jadwal', backref='profil', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'nama': self.nama, 'aktif': self.aktif}


class AudioFile(db.Model):
    __tablename__ = 'audio_file'
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(200), nullable=False)
    path = db.Column(db.String(500))    # local path or YouTube URL
    tipe = db.Column(db.String(10))     # 'lokal' or 'youtube'

    def to_dict(self):
        return {
            'id': self.id,
            'nama': self.nama,
            'path': self.path,
            'tipe': self.tipe,
        }


class Jadwal(db.Model):
    __tablename__ = 'jadwal'
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    waktu = db.Column(db.String(5), nullable=False)         # HH:MM
    # Bitmask hari: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64
    hari = db.Column(db.Integer, nullable=False, default=31)
    audio_id = db.Column(db.Integer, db.ForeignKey('audio_file.id'), nullable=True)
    profil_id = db.Column(db.Integer, db.ForeignKey('profil.id'), nullable=True)
    durasi_menit = db.Column(db.Integer, default=1)
    aktif = db.Column(db.Boolean, default=True)
    audio = db.relationship('AudioFile', backref='jadwal')

    def to_dict(self):
        return {
            'id': self.id,
            'nama': self.nama,
            'waktu': self.waktu,
            'hari': self.hari,
            'audio_id': self.audio_id,
            'audio_nama': self.audio.nama if self.audio else None,
            'audio_tipe': self.audio.tipe if self.audio else None,
            'durasi_menit': self.durasi_menit,
            'aktif': self.aktif,
        }


class KalenderLibur(db.Model):
    __tablename__ = 'kalender_libur'
    id = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.Date, nullable=False, unique=True)
    keterangan = db.Column(db.String(200), default='')


class LogAktivitas(db.Model):
    __tablename__ = 'log_aktivitas'
    id = db.Column(db.Integer, primary_key=True)
    waktu = db.Column(db.DateTime, default=datetime.now)
    aksi = db.Column(db.String(200))
    status = db.Column(db.String(50), default='OK')
