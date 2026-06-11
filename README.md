# Bell Sekolah Otomatis — Armbian Linux (STB HG680P)

Sistem bel sekolah otomatis berbasis web (*Web UI*) yang dirancang khusus untuk berjalan di perangkat hemat daya seperti STB HG680P yang menggunakan sistem operasi Armbian Linux (Debian/Ubuntu). 

Sistem ini mendukung pemutaran bel lokal (MP3/WAV) serta pemutaran musik/audio langsung dari YouTube untuk jam istirahat secara otomatis.

---

## Fitur Utama

- 📅 **Manajemen Jadwal Bel**: Menambah, mengubah, mengaktifkan/menonaktifkan, dan menghapus jadwal bel dengan mudah.
- 📆 **Hari Aktif & Profil Harian**: Mengatur jadwal aktif berdasarkan hari tertentu (Senin–Kamis, Jumat, Sabtu, dll).
- 🏝 **Kalender Libur Otomatis**: Menentukan tanggal libur (hari besar/libur sekolah) agar bel tidak berbunyi secara otomatis pada hari tersebut.
- 🔔 **Manajemen Audio Lokal**: Unggah file bel sekolah Anda sendiri (WAV/MP3) langsung dari antarmuka web.
- 🎵 **Integrasi YouTube**: Cari lagu/audio dari YouTube langsung dari aplikasi, simpan, atau putar secara *live* untuk lagu istirahat.
- 🔊 **Volume Control**: Mengatur volume speaker sekolah langsung dari dashboard Web UI.
- 🛑 **Tombol Darurat (Test & Stop)**: Tombol untuk membunyikan bel secara manual (*Test Bel*) dan menghentikan audio darurat (*Stop Audio*).
- ⚙️ **Autostart (Systemd)**: Berjalan otomatis di latar belakang (*background service*) saat STB dinyalakan (*booting*).
- ☀️ **Desain Flat & Light Mode**: Desain antarmuka cerah (*light theme*) yang modern, bersih, bebas dari efek shadow/gradasi yang berat.
- 🛡 **Double-Click Delete**: Perlindungan hapus jadwal/audio secara inline untuk mencegah salah klik tanpa memicu pop-up dialog browser.

---

## Teknologi yang Digunakan

- **Backend**: Python 3, Flask (Web Framework)
- **Scheduler**: APScheduler (Advanced Python Scheduler)
- **Database**: SQLite (SQLAlchemy)
- **Audio Engine**:
  - **Linux**: `mpg123` (MP3), `aplay`/`paplay` (WAV/OGG), `mpv` + `yt-dlp` (YouTube stream)
  - **Windows (Testing)**: PowerShell `System.Windows.Media.MediaPlayer` + local download cache `yt-dlp` (M4A)
- **Frontend**: HTML5, Vanilla CSS (Flat Theme), Vanilla JS

---

## 💻 Tata Cara Pengujian Lokal (Windows)

Sebelum dideploy ke STB HG680P, Anda dapat mencobanya terlebih dahulu di komputer lokal Windows:

### Prasyarat
- Pastikan **Python 3.10+** sudah terinstal.

### Langkah-Langkah:
1. **Buat Virtual Environment & Aktifkan**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```
2. **Instal Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```
3. **Generate Audio Sampel**:
   Jalankan script berikut untuk membuat file audio sampel bel sekolah:
   ```powershell
   python generate_bell.py
   ```
4. **Jalankan Server**:
   ```powershell
   python app.py
   ```
5. Buka browser Anda dan akses:
   👉 **[http://localhost:5000](http://localhost:5000)**

---

## 📟 Tata Cara Instalasi di STB HG680P (Armbian)

### Prasyarat
- Koneksi STB ke jaringan lokal (LAN/Wi-Fi).
- Hubungkan output **Audio Jack (3.5mm)** STB ke **Amplifier** dan **Speaker Sekolah**.
- Hubungkan STB ke internet (untuk instalasi dan pemutaran YouTube).

### Langkah-Langkah Instalasi:
1. Buka terminal SSH ke STB Anda.
2. Kloning repositori ini ke STB:
   ```bash
   git clone https://github.com/yusufburhani20/belsekolah.git
   ```
3. Masuk ke direktori projek:
   ```bash
   cd belsekolah
   ```
4. Jalankan script instalasi otomatis sebagai **root**:
   ```bash
   sudo bash install.sh
   ```
   *Script ini akan otomatis menginstall dependencies sistem (`python3`, `mpv`, `mpg123`, `alsa-utils`, `ffmpeg`), membuat folder `/opt/bell/`, mengkopi semua kode, menginstall requirements Python, dan mendaftarkan systemd service.*

5. Buka web browser dari komputer lain di jaringan yang sama dan akses:
   ```text
   http://<IP_STB_ANDA>:5000
   ```

---

## 🛠 Perintah Pengelolaan Service di Armbian

Anda dapat mengelola service bel sekolah menggunakan perintah systemd standar berikut:

- **Mengecek Status Service**:
  ```bash
  sudo systemctl status bell
  ```
- **Melihat Log Aktivitas Real-time**:
  ```bash
  sudo journalctl -u bell -f
  ```
- **Restart Service**:
  ```bash
  sudo systemctl restart bell
  ```
- **Menghentikan Service**:
  ```bash
  sudo systemctl stop bell
  ```

---

## Lisensi
Projek ini dibuat untuk kepentingan sekolah dan dikembangkan secara open-source.
