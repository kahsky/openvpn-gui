#!/usr/bin/env bash
# ============================================================
#  build_deb.sh — Construit le paquet .deb pour OpenVPN GUI
#
#  Usage :
#    ./build_deb.sh              # construit seulement
#    ./build_deb.sh --install    # construit ET installe avec apt
#
#  Prérequis : dpkg-deb + fakeroot  (installés ci-dessous si absents)
# ============================================================
set -euo pipefail

# ── Couleurs ────────────────────────────────────────────────────────────── #
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR ]${NC}  $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}▶ $*${NC}"; }

# ── Configuration ───────────────────────────────────────────────────────── #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_NAME="openvpn-gui"
VERSION="1.0.1"
ARCH="all"
MAINTAINER="Karl <kahsky@book>"
DESCRIPTION_SHORT="Client OpenVPN graphique pour Linux Mint / Ubuntu"
DESCRIPTION_LONG=" Interface GTK3 moderne pour gérer des connexions OpenVPN.
 Importation de fichiers .ovpn, stockage sécurisé des identifiants
 dans le trousseau système (GNOME Keyring), icône dans la barre système
 (verte = connecté, grise = déconnecté) et intégration NetworkManager."

BUILD_ROOT="${SCRIPT_DIR}/build"
PKG_DIR="${BUILD_ROOT}/${PKG_NAME}_${VERSION}_${ARCH}"
DEB_OUT="${BUILD_ROOT}/${PKG_NAME}_${VERSION}_${ARCH}.deb"

DO_INSTALL=false
[[ "${1:-}" == "--install" ]] && DO_INSTALL=true

# ── Vérifications / installation des outils de build ─────────────────────── #
step "Vérifications"

# fakeroot est l'outil standard pour builder des .deb sans être root
# (il simule l'ownership root:root dans l'archive tar du .deb)
# Si on n'est pas root, on a besoin de fakeroot pour simuler root:root dans le .deb
# Si on est root, dpkg-deb peut être appelé directement.
if [[ $EUID -ne 0 ]]; then
    if ! command -v fakeroot &>/dev/null; then
        warn "fakeroot absent — installation…"
        sudo apt-get install -y --no-install-recommends fakeroot
    fi
    command -v fakeroot &>/dev/null || error "fakeroot introuvable après tentative d'installation."
fi
command -v dpkg-deb &>/dev/null || error "dpkg-deb introuvable (paquet 'dpkg' requis)."

# Vérifier que les sources sont présentes
for src in openvpn_gui assets openvpn-gui; do
    [[ -e "${SCRIPT_DIR}/${src}" ]] || error "Fichier/dossier source manquant : ${src}"
done

# Vérification syntaxique Python
python3 -c "
import ast, sys, pathlib, os
os.chdir('${SCRIPT_DIR}')
fails = []
for f in pathlib.Path('openvpn_gui').rglob('*.py'):
    try:
        ast.parse(f.read_text())
    except SyntaxError as e:
        fails.append(f'{f}:{e.lineno}: {e.msg}')
if fails:
    print('Erreurs de syntaxe Python :')
    [print(' ', l) for l in fails]
    sys.exit(1)
" || error "Corriger les erreurs Python avant de construire."

success "Vérifications OK."

# ── Nettoyage du dossier de build ────────────────────────────────────────── #
step "Initialisation du dossier de build"

# Si un build précédent a laissé des fichiers owned root, fakeroot s'en chargera.
# Pour le nettoyage du répertoire lui-même on utilise l'utilisateur courant ;
# si des restes root existent, on prévient l'utilisateur.
rm -rf "${PKG_DIR}" 2>/dev/null || {
    # Fichiers owned root et on n'est pas root : on demande sudo
    warn "Anciens fichiers root dans build/ — suppression avec sudo…"
    sudo rm -rf "${PKG_DIR}"
}
rm -f "${DEB_OUT}" 2>/dev/null || sudo rm -f "${DEB_OUT}"

# ── Arborescence du paquet ────────────────────────────────────────────────── #
APP_DIR="${PKG_DIR}/opt/${PKG_NAME}"
BIN_DIR="${PKG_DIR}/usr/bin"
APPLICATIONS="${PKG_DIR}/usr/share/applications"
ICON_DIR="${PKG_DIR}/usr/share/icons/hicolor/scalable/apps"
DOC_DIR="${PKG_DIR}/usr/share/doc/${PKG_NAME}"
DEBIAN_DIR="${PKG_DIR}/DEBIAN"

mkdir -p \
    "${APP_DIR}" \
    "${BIN_DIR}" \
    "${APPLICATIONS}" \
    "${ICON_DIR}" \
    "${DOC_DIR}" \
    "${DEBIAN_DIR}"

info "Arborescence créée."

# ── Copie des fichiers de l'application ─────────────────────────────────── #
step "Copie des fichiers"

cp -rp "${SCRIPT_DIR}/openvpn_gui" "${APP_DIR}/"
cp -rp "${SCRIPT_DIR}/assets"      "${APP_DIR}/"
cp  -p "${SCRIPT_DIR}/openvpn-gui" "${APP_DIR}/openvpn-gui"
cp  -p "${SCRIPT_DIR}/assets/icon_app.svg" "${ICON_DIR}/openvpn-gui.svg"
cp  -p "${SCRIPT_DIR}/README.md"   "${DOC_DIR}/README.md"  2>/dev/null || true
cp  -p "${SCRIPT_DIR}/LICENSE"     "${DOC_DIR}/copyright"  2>/dev/null || true

success "Fichiers copiés."

# ── Wrapper /usr/bin/openvpn-gui ─────────────────────────────────────────── #
step "Création du lanceur système"

cat > "${BIN_DIR}/openvpn-gui" << 'LAUNCHER'
#!/bin/sh
exec python3 /opt/openvpn-gui/openvpn-gui "$@"
LAUNCHER

success "Lanceur : /usr/bin/openvpn-gui"

# ── Entrée .desktop ──────────────────────────────────────────────────────── #
step "Création de l'entrée .desktop"

cat > "${APPLICATIONS}/openvpn-gui.desktop" << DESKTOP
[Desktop Entry]
Name=OpenVPN GUI
GenericName=Client VPN
Comment=${DESCRIPTION_SHORT}
Exec=/usr/bin/openvpn-gui
Icon=openvpn-gui
Terminal=false
Type=Application
Categories=Network;Security;
Keywords=vpn;openvpn;reseau;securite;
StartupNotify=false
DESKTOP

success "Fichier .desktop créé."

# ── Permissions (avant calcul de taille) ─────────────────────────────────── #
step "Application des permissions"

# Répertoires
find "${PKG_DIR}"  -type d                                  -exec chmod 755 {} \;
# Scripts Python : lecture seule
find "${APP_DIR}/openvpn_gui" -name "*.py"                 -exec chmod 644 {} \;
# Assets SVG : lecture seule
find "${APP_DIR}/assets" -type f                            -exec chmod 644 {} \;
find "${ICON_DIR}"       -type f                            -exec chmod 644 {} \;
# Documentation
find "${DOC_DIR}"        -type f                            -exec chmod 644 {} \;
# .desktop
chmod 644 "${APPLICATIONS}/openvpn-gui.desktop"
# Exécutables
chmod 755 "${APP_DIR}/openvpn-gui"
chmod 755 "${BIN_DIR}/openvpn-gui"

success "Permissions OK."

# ── Calcul de la taille installée ────────────────────────────────────────── #
INSTALLED_SIZE=$(du -sk "${PKG_DIR}" | awk '{print $1}')

# ── DEBIAN/control ───────────────────────────────────────────────────────── #
step "Génération de DEBIAN/control"

cat > "${DEBIAN_DIR}/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: python3 (>= 3.10),
 python3-gi,
 python3-gi-cairo,
 gir1.2-gtk-3.0,
 gir1.2-gdkpixbuf-2.0,
 network-manager,
 network-manager-openvpn,
 openvpn,
 libsecret-1-0,
 python3-keyring,
 python3-secretstorage,
 gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1
Recommends: gnome-keyring
Suggests: network-manager-openvpn-gnome
Maintainer: ${MAINTAINER}
Description: ${DESCRIPTION_SHORT}
${DESCRIPTION_LONG}
Homepage: https://github.com/kahsky/openvpn-gui
CONTROL

success "control écrit."

# ── DEBIAN/postinst ──────────────────────────────────────────────────────── #
cat > "${DEBIAN_DIR}/postinst" << 'POSTINST'
#!/bin/sh
set -e
chmod 755 /opt/openvpn-gui/openvpn-gui
chmod 755 /usr/bin/openvpn-gui
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
echo ""
echo "  OpenVPN GUI installe avec succes !"
echo "  Lancez :  openvpn-gui"
echo "  Ou via le menu Applications > Internet"
echo ""
exit 0
POSTINST
chmod 755 "${DEBIAN_DIR}/postinst"

# ── DEBIAN/prerm ─────────────────────────────────────────────────────────── #
cat > "${DEBIAN_DIR}/prerm" << 'PRERM'
#!/bin/sh
set -e
pkill -f "python3.*openvpn-gui" 2>/dev/null || true
exit 0
PRERM
chmod 755 "${DEBIAN_DIR}/prerm"

# ── DEBIAN/postrm ────────────────────────────────────────────────────────── #
cat > "${DEBIAN_DIR}/postrm" << 'POSTRM'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
if [ "$1" = "purge" ]; then
    echo "Note : supprimez ~/.config/openvpn-gui pour effacer votre configuration."
fi
exit 0
POSTRM
chmod 755 "${DEBIAN_DIR}/postrm"

success "Scripts DEBIAN (postinst / prerm / postrm) écrits."

# ── Construction du .deb avec fakeroot ──────────────────────────────────── #
# fakeroot fait croire à dpkg-deb que les fichiers sont owned root:root
# sans nécessiter de droits root réels.
step "Construction du .deb avec fakeroot"

mkdir -p "${BUILD_ROOT}"
if [[ $EUID -eq 0 ]]; then
    dpkg-deb --build "${PKG_DIR}" "${DEB_OUT}"
else
    fakeroot dpkg-deb --build "${PKG_DIR}" "${DEB_OUT}"
fi

# ── Vérification du paquet produit ───────────────────────────────────────── #
step "Vérification du paquet"
dpkg-deb --info "${DEB_OUT}"

# ── Résumé ───────────────────────────────────────────────────────────────── #
DEB_SIZE=$(du -sh "${DEB_OUT}" | awk '{print $1}')
DEB_FILE="${DEB_OUT##*/}"
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Paquet .deb construit avec succes !                     ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
printf  "${GREEN}║${NC}  Fichier   : %-43s${GREEN}║${NC}\n" "${DEB_FILE}"
printf  "${GREEN}║${NC}  Taille    : %-43s${GREEN}║${NC}\n" "${DEB_SIZE}"
printf  "${GREEN}║${NC}  Dossier   : %-43s${GREEN}║${NC}\n" "build/"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Installation :                                          ║${NC}"
echo -e "${GREEN}║    sudo apt install ./build/${DEB_FILE}  ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Desinstallation :                                       ║${NC}"
echo -e "${GREEN}║    sudo apt remove openvpn-gui                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Installation automatique (option --install) ──────────────────────────── #
if $DO_INSTALL; then
    step "Installation avec apt"
    info "apt installera automatiquement toutes les dependances manquantes."
    if [[ $EUID -eq 0 ]]; then
        apt install -y "${DEB_OUT}"
    else
        sudo apt install -y "${DEB_OUT}"
    fi

    success "OpenVPN GUI installe. Lancez : openvpn-gui"
fi
