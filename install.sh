#!/bin/bash
# install.sh — Setup Bell Sekolah di Armbian (HG680P)
# Jalankan dengan: bash install.sh

set -e

INSTALL_DIR="/opt/bell"
SERVICE_FILE="$INSTALL_DIR/bell.service"

echo "════════════════════════════════════════"
echo "  🔔  Bell Sekolah — Installer"
echo "════════════════════════════════════════"

# 1. Update & install system dependencies
echo "[1/5] Menginstall dependensi sistem..."
apt-get update -q
apt-get install -y python3 python3-pip mpv mpg123 alsa-utils ffmpeg

# 2. Create install directory & copy files
echo "[2/5] Menyalin file ke $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"
chown -R root:root "$INSTALL_DIR"

# 3. Install Python packages
echo "[3/5] Menginstall Python packages..."
pip3 install -r "$INSTALL_DIR/requirements.txt" --break-system-packages 2>/dev/null \
  || pip3 install -r "$INSTALL_DIR/requirements.txt"

# 4. Install & enable systemd service
echo "[4/5] Menginstall systemd service..."
cp "$SERVICE_FILE" /etc/systemd/system/bell.service
systemctl daemon-reload
systemctl enable bell
systemctl start bell

# 5. Done
echo ""
echo "[5/5] ✅ Instalasi selesai!"
echo ""
echo "  Web UI tersedia di: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "  Perintah berguna:"
echo "  systemctl status bell      → cek status"
echo "  journalctl -u bell -f      → lihat log"
echo "  systemctl restart bell     → restart"
echo ""
