from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
import logging

logger = logging.getLogger(__name__)

# Mon=0…Sun=6 → cron day names
_HARI_CRON = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

scheduler = BackgroundScheduler(timezone='Asia/Jakarta')


def bitmask_to_cron_days(bitmask: int) -> str:
    """Convert bitmask (Mon=bit0, Tue=bit1, …) to cron day-of-week string."""
    return ','.join(_HARI_CRON[i] for i in range(7) if bitmask & (1 << i))


def init_scheduler(app, db, audio_engine):
    """
    Initialize APScheduler. Registers all active schedules from the database.
    Returns a `reload()` callable to refresh schedules after DB changes.
    """
    from models import Jadwal, KalenderLibur, LogAktivitas

    def _ring(jadwal_id: int):
        """Callback fired by the scheduler at the scheduled time."""
        with app.app_context():
            j = db.session.get(Jadwal, jadwal_id)
            if not j or not j.aktif:
                return

            today = date.today()
            libur = KalenderLibur.query.filter_by(tanggal=today).first()

            if libur:
                logger.info(f"Hari libur ({libur.keterangan}) — bel dilewati: {j.nama}")
                log = LogAktivitas(aksi=f"Dilewati (libur: {libur.keterangan}): {j.nama}", status="SKIP")
            else:
                if j.audio:
                    if j.audio.tipe == 'youtube':
                        audio_engine.play_youtube(j.audio.path, j.durasi_menit)
                    else:
                        audio_engine.play_local(j.audio.path, j.durasi_menit)
                logger.info(f"🔔 Bel: {j.nama} @ {j.waktu}")
                log = LogAktivitas(aksi=f"Bel: {j.nama}", status="OK")

            db.session.add(log)
            db.session.commit()

    def reload():
        """Remove all scheduled jobs and reload from DB."""
        scheduler.remove_all_jobs()
        with app.app_context():
            jadwal_list = Jadwal.query.filter_by(aktif=True).all()
            count = 0
            for j in jadwal_list:
                days_str = bitmask_to_cron_days(j.hari)
                if not days_str:
                    continue
                hour, minute = j.waktu.split(':')
                scheduler.add_job(
                    _ring,
                    CronTrigger(
                        hour=int(hour),
                        minute=int(minute),
                        day_of_week=days_str,
                        timezone='Asia/Jakarta',
                    ),
                    args=[j.id],
                    id=f'jadwal_{j.id}',
                    replace_existing=True,
                    misfire_grace_time=60,
                )
                count += 1
            logger.info(f"Scheduler: {count} jadwal aktif dimuat")

    reload()

    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started (Asia/Jakarta timezone)")

    return reload


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
