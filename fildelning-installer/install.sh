#!/bin/bash

set -e

INSTALL_DIR="/opt/fildelning"
STATE_DIR="/var/lib/fildelning"
LOG_DIR="/var/log/fildelning"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo
echo "======================================"
echo "       Fildelning Installer"
echo "======================================"
echo

# --------------------------------------------------
# Check root
# --------------------------------------------------

if [ "$EUID" -ne 0 ]; then
    echo "Run the installer with:"
    echo
    echo "    sudo ./install.sh"
    echo
    exit 1
fi

# --------------------------------------------------
# Determine normal user
# --------------------------------------------------

CURRENT_USER="${SUDO_USER:-}"

if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
    echo "ERROR: Run this using sudo from a normal user account."
    echo
    echo "Example:"
    echo "    sudo ./install.sh"
    echo
    exit 1
fi

CURRENT_GROUP="$(id -gn "$CURRENT_USER")"

echo "Installing for user:"
echo "  $CURRENT_USER"
echo

# --------------------------------------------------
# Check installer files
# --------------------------------------------------

echo "[1/9] Checking installer files..."

required_files=(
    "$SCRIPT_DIR/opt/fildelning/shares.py"
    "$SCRIPT_DIR/opt/fildelning/file_utils.py"
    "$SCRIPT_DIR/opt/fildelning/share_server.py"
    "$SCRIPT_DIR/opt/fildelning/receive_server.py"
    "$SCRIPT_DIR/opt/fildelning/share"
    "$SCRIPT_DIR/opt/fildelning/receive"
    "$SCRIPT_DIR/opt/fildelning/gui/gui.py"
    "$SCRIPT_DIR/opt/fildelning/gui/gui_actions.py"
    "$SCRIPT_DIR/opt/fildelning/gui/dir_picker.py"
    "$SCRIPT_DIR/systemd/share.service"
    "$SCRIPT_DIR/systemd/receive.service"
    "$SCRIPT_DIR/desktop/fildelning.desktop"
)

for file in "${required_files[@]}"; do

    if [ ! -f "$file" ]; then
        echo
        echo "ERROR: Missing file:"
        echo "$file"
        exit 1
    fi

done

echo "OK."

# --------------------------------------------------
# Create directories
# --------------------------------------------------

echo
echo "[2/9] Creating directories..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/gui"
mkdir -p "$STATE_DIR"
mkdir -p "$LOG_DIR"

# --------------------------------------------------
# Install program
# --------------------------------------------------

echo
echo "[3/9] Installing program files..."

cp -a "$SCRIPT_DIR/opt/fildelning/." "$INSTALL_DIR/"

# Never install old share/receive state
rm -f "$INSTALL_DIR/shares.json"
rm -f "$INSTALL_DIR/receives.json"

# --------------------------------------------------
# Permissions
# --------------------------------------------------

echo
echo "[4/9] Setting program permissions..."

chmod 755 "$INSTALL_DIR/share"
chmod 755 "$INSTALL_DIR/receive"

chmod 644 "$INSTALL_DIR"/*.py
chmod 644 "$INSTALL_DIR/gui"/*.py

chown -R "$CURRENT_USER:$CURRENT_GROUP" "$INSTALL_DIR"
chown -R "$CURRENT_USER:$CURRENT_GROUP" "$STATE_DIR"
chown -R "$CURRENT_USER:$CURRENT_GROUP" "$LOG_DIR"

# --------------------------------------------------
# Command symlinks
# --------------------------------------------------

echo
echo "[5/9] Installing commands..."

ln -sf "$INSTALL_DIR/share" /usr/local/bin/share
ln -sf "$INSTALL_DIR/receive" /usr/local/bin/receive

# --------------------------------------------------
# GUI desktop integration
# --------------------------------------------------

echo
echo "[6/9] Installing GUI desktop entry..."

sed "s|@INSTALL_DIR@|$INSTALL_DIR|g" \
    "$SCRIPT_DIR/desktop/fildelning.desktop" \
    > /usr/share/applications/fildelning.desktop

chmod 644 /usr/share/applications/fildelning.desktop

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi

# --------------------------------------------------
# Install systemd services
# --------------------------------------------------

echo
echo "[7/9] Installing systemd services..."

sed "s/@USERNAME@/$CURRENT_USER/g" \
    "$SCRIPT_DIR/systemd/share.service" \
    > /etc/systemd/system/share.service

sed "s/@USERNAME@/$CURRENT_USER/g" \
    "$SCRIPT_DIR/systemd/receive.service" \
    > /etc/systemd/system/receive.service

# --------------------------------------------------
# systemd
# --------------------------------------------------

echo
echo "[8/9] Configuring systemd..."

systemctl daemon-reload

systemctl enable share.service
systemctl enable receive.service

systemctl restart share.service
systemctl restart receive.service

# --------------------------------------------------
# Done
# --------------------------------------------------

echo
echo "[9/9] Installation complete!"
echo

echo "======================================"
echo "Local servers"
echo "======================================"
echo
echo "Share:"
echo "  http://127.0.0.1:8000"
echo
echo "Receive:"
echo "  http://127.0.0.1:8001"
echo

echo "Commands:"
echo
echo "  share \"/path/to/directory\""
echo "  receive \"/path/to/directory\""
echo

echo "GUI:"
echo
echo "  Sök efter \"Fildelning\" i programmenyn, eller kör:"
echo "  python3 $INSTALL_DIR/gui/gui.py"
echo

echo "Services:"
echo
echo "  sudo systemctl status share"
echo "  sudo systemctl status receive"
echo
