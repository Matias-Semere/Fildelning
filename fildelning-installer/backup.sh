#!/bin/bash

set -e

BACKUP_ROOT="$HOME/fildelnings-grejer/backups"
DATE="$(date '+%Y-%m-%d_%H-%M-%S')"

BACKUP_DIR="$BACKUP_ROOT/fildelning-$DATE"
ARCHIVE="$BACKUP_ROOT/fildelning-$DATE.tar.gz"

echo
echo "======================================"
echo "       Fildelning Backup"
echo "======================================"
echo

mkdir -p "$BACKUP_DIR/fildelning"
mkdir -p "$BACKUP_DIR/systemd"
mkdir -p "$BACKUP_DIR/state"

echo "[1/6] Kopierar programfiler..."

sudo cp -a /opt/fildelning/. \
    "$BACKUP_DIR/fildelning/"

echo "[2/6] Kopierar systemd-filer..."

sudo cp /etc/systemd/system/share.service \
    "$BACKUP_DIR/systemd/"

sudo cp /etc/systemd/system/receive.service \
    "$BACKUP_DIR/systemd/"

echo "[3/6] Kopierar state..."

if [ -f /var/lib/fildelning/shares.json ]; then
    sudo cp /var/lib/fildelning/shares.json \
        "$BACKUP_DIR/state/"
fi

if [ -f /var/lib/fildelning/receives.json ]; then
    sudo cp /var/lib/fildelning/receives.json \
        "$BACKUP_DIR/state/"
fi

echo "[4/6] Kopierar konfiguration..."

if [ -f /etc/fildelning.conf ]; then
    sudo cp /etc/fildelning.conf \
        "$BACKUP_DIR/"
fi

echo "[5/6] Skapar arkiv..."

sudo chown -R "$USER:$USER" "$BACKUP_DIR"

tar -czf "$ARCHIVE" \
    -C "$BACKUP_ROOT" \
    "$(basename "$BACKUP_DIR")"

rm -rf "$BACKUP_DIR"

echo "[6/6] Rensar gamla säkerhetskopior (äldre än 14 dagar)..."

find "$BACKUP_ROOT" -maxdepth 1 -name "fildelning-*.tar.gz" -mtime +14 -delete

echo
echo "======================================"
echo "Backup klar!"
echo "======================================"
echo
echo "Arkiv:"
echo "  $ARCHIVE"
echo
echo "Storlek:"
du -h "$ARCHIVE"
echo