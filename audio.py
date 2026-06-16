import subprocess
import threading
import logging
import os

logger = logging.getLogger(__name__)


def _get_selected_device():
    try:
        from models import Pengaturan
        return Pengaturan.get_val('audio_device', 'default')
    except Exception:
        return 'default'


class AudioEngine:
    """
    Manages audio playback via system commands.
    Supports:
      - Local files via mpg123 (MP3) or aplay (WAV/OGG)
      - YouTube/web streams via mpv + yt-dlp
    Volume control via ALSA amixer or PulseAudio pactl.
    """

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self._stop_timer = None

    def _kill_current(self):
        """Terminate any running audio process."""
        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def _schedule_stop(self, seconds: float):
        """Auto-stop after given seconds."""
        def _stop():
            self.stop()
        self._stop_timer = threading.Timer(seconds, _stop)
        self._stop_timer.daemon = True
        self._stop_timer.start()

    def _ensure_hardware_audio_on(self):
        """Ensure analog codec is unmuted, active, and AV output jack is powered ON (Linux only)."""
        if os.name != 'nt':
            try:
                subprocess.run(['amixer', '-c', '0', '-q', 'sset', 'AIU ACODEC SRC', 'I2S'], capture_output=True)
                subprocess.run(['amixer', '-c', '0', '-q', 'sset', 'AIU ACODEC OUT EN', 'on'], capture_output=True)
                subprocess.run(['amixer', '-c', '0', '-q', 'sset', 'ACODEC', 'unmute'], capture_output=True)
            except Exception as e:
                logger.debug(f"Failed to ensure hardware audio: {e}")

    def play_local(self, path: str, duration_minutes: float = None):
        """Play a local audio file. Optionally auto-stop after duration_minutes."""
        with self._lock:
            self._kill_current()
            self._ensure_hardware_audio_on()
            ext = os.path.splitext(path)[1].lower()
            device = _get_selected_device()
            try:
                if os.name == 'nt':
                    # Windows playback using built-in PowerShell MediaPlayer (supports WAV and MP3)
                    abs_path = os.path.abspath(path).replace("'", "''")
                    ps_script = (
                        f"Add-Type -AssemblyName PresentationCore; "
                        f"$p = New-Object System.Windows.Media.MediaPlayer; "
                        f"$p.Open('{abs_path}'); "
                        f"$p.Play(); "
                        f"Start-Sleep -Seconds 1; "
                        f"while ($p.NaturalDuration.HasTimeSpan -eq $false -and $p.Position.TotalSeconds -lt 2) {{ Start-Sleep -Milliseconds 100 }}; "
                        f"if ($p.NaturalDuration.HasTimeSpan) {{ "
                        f"  $duration = $p.NaturalDuration.TimeSpan.TotalSeconds; "
                        f"  Start-Sleep -Seconds ($duration - 1); "
                        f"}} else {{ "
                        f"  Start-Sleep -Seconds 300; "
                        f"}}"
                    )
                    self._process = subprocess.Popen(
                        ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    logger.info(f"▶ Playing local (Windows - Device: {device}): {path}")
                else:
                    cmd = ['mpv', '--no-video', '--quiet']
                    if device and device != 'default':
                        cmd.append(f'--audio-device=alsa/{device}')
                    cmd.append(path)
                    self._process = subprocess.Popen(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    logger.info(f"▶ Playing local (device: {device}): {path}")

                if duration_minutes:
                    self._schedule_stop(duration_minutes * 60)
            except FileNotFoundError:
                # Fallback: try paplay (PulseAudio)
                try:
                    if device and device != 'default':
                        cmd = ['paplay', '-d', device, path]
                    else:
                        cmd = ['paplay', path]
                    self._process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    logger.error(f"Audio playback failed: {e}")

    def play_youtube(self, url_or_query: str, duration_minutes: float = None):
        """Stream audio from YouTube URL or search query via mpv + yt-dlp (Linux) or PowerShell MediaPlayer (Windows)."""
        with self._lock:
            try:
                if os.name == 'nt':
                    logger.info(f"Resolving YouTube direct URL and downloading locally: {url_or_query}")
                    
                    # 1. Kill current player to release any lock on the temp file
                    self._kill_current()
                    
                    # 2. Setup download path
                    import yt_dlp
                    sound_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'sounds')
                    os.makedirs(sound_dir, exist_ok=True)
                    
                    # Delete old temp files to prevent issues
                    tmp_base = os.path.join(sound_dir, 'tmp_youtube')
                    for ext in ['m4a', 'webm', 'mp3', 'wav']:
                        old_file = f"{tmp_base}.{ext}"
                        if os.path.exists(old_file):
                            try:
                                os.remove(old_file)
                            except Exception:
                                pass
                    
                    ydl_opts = {
                        'format': 'bestaudio[ext=m4a]/bestaudio',
                        'outtmpl': os.path.join(sound_dir, 'tmp_youtube.%(ext)s'),
                        'quiet': True,
                        'no_warnings': True,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        search_query = url_or_query if url_or_query.startswith('http') else f"ytsearch1:{url_or_query}"
                        info = ydl.extract_info(search_query, download=True)
                        if 'entries' in info:
                            entry = info['entries'][0]
                        else:
                            entry = info
                        
                        actual_ext = entry.get('ext', 'm4a')
                        downloaded_file = os.path.join(sound_dir, f'tmp_youtube.{actual_ext}')
                        actual_title = entry.get('title', 'YouTube Audio')
                    
                    # 3. Play the downloaded local file using PowerShell MediaPlayer
                    abs_path = os.path.abspath(downloaded_file).replace("'", "''")
                    ps_script = (
                        f"Add-Type -AssemblyName PresentationCore; "
                        f"$p = New-Object System.Windows.Media.MediaPlayer; "
                        f"$p.Open('{abs_path}'); "
                        f"$p.Play(); "
                        f"Start-Sleep -Seconds 1; "
                        f"while ($p.NaturalDuration.HasTimeSpan -eq $false -and $p.Position.TotalSeconds -lt 2) {{ Start-Sleep -Milliseconds 100 }}; "
                        f"if ($p.NaturalDuration.HasTimeSpan) {{ "
                        f"  $duration = $p.NaturalDuration.TimeSpan.TotalSeconds; "
                        f"  Start-Sleep -Seconds ($duration - 1); "
                        f"}} else {{ "
                        f"  Start-Sleep -Seconds 300; "
                        f"}}"
                    )
                    self._process = subprocess.Popen(
                        ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    logger.info(f"▶ Streaming YouTube (Windows - Local Temp): {actual_title}")
                else:
                    self._kill_current()
                    self._ensure_hardware_audio_on()
                    is_url = url_or_query.startswith('http')
                    source = url_or_query if is_url else f'ytdl://ytsearch1:{url_or_query}'
                    device = _get_selected_device()
                    cmd = [
                        'mpv',
                        '--no-video',
                        '--quiet',
                        '--ytdl-format=bestaudio/best',
                    ]
                    if device and device != 'default':
                        cmd.append(f'--audio-device=alsa/{device}')
                    cmd.append(source)
                    if duration_minutes:
                        cmd.append(f'--length={int(duration_minutes * 60)}')
                    self._process = subprocess.Popen(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    logger.info(f"▶ Streaming YouTube (device: {device}): {url_or_query}")

                if duration_minutes:
                    self._schedule_stop(duration_minutes * 60)
            except FileNotFoundError:
                logger.error("mpv not found. On Windows, make sure mpv is installed and in PATH. On Linux: sudo apt install mpv")
            except Exception as e:
                logger.error(f"YouTube playback error: {e}")

    def stop(self):
        """Stop any playing audio immediately."""
        with self._lock:
            self._kill_current()
            logger.info("⏹ Audio stopped")

    def set_volume(self, level: int) -> bool:
        """Set system volume (0–100). Tries ALSA first, then PulseAudio."""
        level = max(0, min(100, level))
        try:
            from models import Pengaturan
            Pengaturan.set_val('volume', level)
        except Exception as e:
            logger.error(f"Failed to save volume to database: {e}")

        if os.name == 'nt':
            logger.info(f"🔊 Volume control is simulated on Windows (requested {level}%)")
            return True
        try:
            subprocess.run(
                ['amixer', '-c', '0', '-q', 'sset', 'AIU ACODEC SRC', 'I2S'],
                capture_output=True
            )
            subprocess.run(
                ['amixer', '-c', '0', '-q', 'sset', 'ACODEC', f'{level}%', 'unmute'],
                check=True, capture_output=True
            )
            subprocess.run(
                ['amixer', '-c', '0', '-q', 'sset', 'AIU ACODEC OUT EN', 'on'],
                capture_output=True
            )
            logger.info(f"🔊 Volume set to {level}% via amixer")
            return True
        except Exception:
            try:
                subprocess.run(
                    ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{level}%'],
                    check=True, capture_output=True
                )
                logger.info(f"🔊 Volume set to {level}% via pactl")
                return True
            except Exception as e:
                logger.error(f"Volume control failed: {e}")
                return False

    def is_playing(self) -> bool:
        """Returns True if audio is currently playing."""
        return self._process is not None and self._process.poll() is None


audio_engine = AudioEngine()
