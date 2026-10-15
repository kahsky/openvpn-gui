#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  build_rpm.sh — Construit le paquet RPM (Fedora et dérivés, noarch) d'OpenVPN GUI
#                 depuis n'importe quelle distribution.
#
#  Usage : ./build_rpm.sh   →  build/openvpn-gui-<VERSION>-1.noarch.rpm
#  Prérequis : rpmbuild (paquet « rpm » sur Debian/Mint : sudo apt install rpm)
#  Les fichiers viennent de build_deb.sh --stage-only (même arborescence que le .deb).
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
APP_NAME="openvpn-gui"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(sed -n 's/^VERSION="\(.*\)"/\1/p' "$SCRIPT_DIR/build_deb.sh" | head -1)"
command -v rpmbuild >/dev/null 2>&1 || { echo "rpmbuild absent : sudo apt install rpm" >&2; exit 2; }
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC="$WORK/${APP_NAME}-${VERSION}"
mkdir -p "$SRC" "$WORK/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
"$SCRIPT_DIR/build_deb.sh" --stage-only "$SRC/tree" >/dev/null
tar -C "$WORK" -czf "$WORK/rpmbuild/SOURCES/${APP_NAME}-${VERSION}.tar.gz" "${APP_NAME}-${VERSION}"
rpmbuild -bb --define "_topdir $WORK/rpmbuild" --define "version $VERSION" --define "dist %{nil}" \
         "$SCRIPT_DIR/${APP_NAME}.spec" >/dev/null
OUT="$(ls "$WORK"/rpmbuild/RPMS/noarch/${APP_NAME}-${VERSION}-1*.noarch.rpm | head -1)"
mkdir -p "$SCRIPT_DIR/build"
FINAL="$SCRIPT_DIR/build/${APP_NAME}-${VERSION}-1.noarch.rpm"
cp -f "$OUT" "$FINAL"
echo "══════════════════════════════════════════"
echo "  ✅ RPM construit : build/$(basename "$FINAL") ($(du -h "$FINAL" | cut -f1))"
echo "  Installer : sudo dnf install ./build/$(basename "$FINAL")"
echo "══════════════════════════════════════════"
