#!/usr/bin/env bash
# ============================================================
#  OpenVPN GUI — Installer for Linux Mint 22.x / Ubuntu 24.x
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/openvpn-gui"
DESKTOP_FILE="/usr/share/applications/openvpn-gui.desktop"
BIN_LINK="/usr/local/bin/openvpn-gui"
ICON_DEST="/usr/share/icons/hicolor/scalable/apps/openvpn-gui.svg"

# ── Root check ───────────────────────────────────────────────────────────── #
if [[ $EUID -ne 0 ]]; then
    error "Please run as root:  sudo ./install.sh"
fi

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       OpenVPN GUI Installer           ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════╝${NC}"
echo ""

# ── System packages ───────────────────────────────────────────────────────── #
info "Installing system dependencies…"

apt-get update -qq

PACKAGES=(
    python3
    python3-pip
    python3-gi
    python3-gi-cairo
    gir1.2-gtk-3.0
    gir1.2-gdkpixbuf-2.0
    network-manager
    network-manager-openvpn
    openvpn
    libsecret-1-0
    libsecret-tools
)

# AppIndicator: try Ayatana first (Ubuntu 22+/Mint 21+), then classic
INDICATOR_PKG=""
if apt-cache show gir1.2-ayatanaappindicator3-0.1 &>/dev/null 2>&1; then
    INDICATOR_PKG="gir1.2-ayatanaappindicator3-0.1"
elif apt-cache show gir1.2-appindicator3-0.1 &>/dev/null 2>&1; then
    INDICATOR_PKG="gir1.2-appindicator3-0.1"
else
    warn "No AppIndicator3 package found — tray icon will use GtkStatusIcon fallback."
fi

[[ -n "$INDICATOR_PKG" ]] && PACKAGES+=("$INDICATOR_PKG")

apt-get install -y --no-install-recommends "${PACKAGES[@]}" > /dev/null
success "System packages installed."

# ── Python packages ───────────────────────────────────────────────────────── #
info "Installing Python packages…"
pip3 install --quiet --break-system-packages keyring secretstorage 2>/dev/null \
    || pip3 install --quiet keyring secretstorage
success "Python packages installed."

# ── Copy application files ────────────────────────────────────────────────── #
info "Installing OpenVPN GUI to ${INSTALL_DIR}…"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/openvpn_gui" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/assets"      "$INSTALL_DIR/"
cp    "$SCRIPT_DIR/openvpn-gui" "$INSTALL_DIR/openvpn-gui"
chmod +x "$INSTALL_DIR/openvpn-gui"
success "Files copied."

# ── Launcher symlink ──────────────────────────────────────────────────────── #
ln -sf "$INSTALL_DIR/openvpn-gui" "$BIN_LINK"
success "Launcher available at: $BIN_LINK"

# ── App icon ──────────────────────────────────────────────────────────────── #
mkdir -p /usr/share/icons/hicolor/scalable/apps
cp "$SCRIPT_DIR/assets/icon_app.svg" "$ICON_DEST"
gtk-update-icon-cache -f /usr/share/icons/hicolor &>/dev/null || true
success "Icon installed."

# ── Desktop entry ─────────────────────────────────────────────────────────── #
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=OpenVPN GUI
GenericName=VPN Client
Comment=Manage OpenVPN connections with a modern GUI
Exec=$BIN_LINK
Icon=openvpn-gui
Terminal=false
Type=Application
Categories=Network;Security;
Keywords=vpn;openvpn;network;security;
StartupNotify=false
EOF
success "Desktop entry created."

# ── Autostart (optional) ──────────────────────────────────────────────────── #
read -rp "$(echo -e "${CYAN}[?]${NC}    Start OpenVPN GUI at login? [y/N]: ")" AUTOSTART
if [[ "${AUTOSTART,,}" == "y" ]]; then
    AUTOSTART_DIR="/etc/xdg/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cp "$DESKTOP_FILE" "$AUTOSTART_DIR/openvpn-gui.desktop"
    success "Autostart entry added."
fi

# ── NetworkManager VPN plugin check ──────────────────────────────────────── #
echo ""
if systemctl is-active --quiet NetworkManager; then
    success "NetworkManager is running."
else
    warn "NetworkManager is not running. Starting it…"
    systemctl enable --now NetworkManager || true
fi

echo ""
echo -e "${GREEN}╔═════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Installation complete!                ║${NC}"
echo -e "${GREEN}║                                         ║${NC}"
echo -e "${GREEN}║   Run:  openvpn-gui                     ║${NC}"
echo -e "${GREEN}║   Or launch from your application menu. ║${NC}"
echo -e "${GREEN}╚═════════════════════════════════════════╝${NC}"
echo ""
