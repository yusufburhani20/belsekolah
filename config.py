import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(BASE_DIR, 'static', 'sounds')
DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "bell.db")}'
DEFAULT_VOLUME = 80
SECRET_KEY = 'bell-sekolah-2024-secret-key'
TIMEZONE = 'Asia/Jakarta'

# Relay GPIO pin (future use — set to None to disable)
RELAY_GPIO_PIN = None
