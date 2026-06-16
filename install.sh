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
apt-get install -y python3 python3-pip mpv mpg123 alsa-utils ffmpeg dnsmasq-base

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

# 5. Konfigurasi default hotspot
echo "Menyiapkan default Hotspot Wi-Fi..."
if command -v nmcli &> /dev/null; then
  WIFI_IFACE=$(nmcli -t -f DEVICE,TYPE device | grep :wifi | head -n1 | cut -d: -f1)
  if [ -n "$WIFI_IFACE" ]; then
    echo "Ditemukan interface Wi-Fi: $WIFI_IFACE"
    nmcli connection delete Hotspot &>/dev/null || true
    if nmcli device wifi hotspot ssid bell password admin123 ifname "$WIFI_IFACE" con-name Hotspot; then
      echo "Default hotspot 'bell' berhasil dibuat!"
      nmcli connection modify Hotspot connection.autoconnect yes
    else
      echo "Gagal membuat default hotspot otomatis."
    fi
  else
    echo "Tidak ditemukan interface Wi-Fi untuk hotspot."
  fi
else
  echo "nmcli tidak ditemukan. Lewati konfigurasi hotspot."
fi

# 6. Done
echo ""
echo "[6/6] ✅ Instalasi selesai!"
echo ""
echo "  Web UI tersedia di: http://\$(hostname -I | awk '{print \$1}'):5000"
echo ""
echo "  Perintah berguna:"
echo "  systemctl status bell      → cek status"
echo "  journalctl -u bell -f      → lihat log"
echo "  systemctl restart bell     → restart"
echo ""
