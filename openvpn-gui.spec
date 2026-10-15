# OpenVPN GUI by Dukiwi — paquet RPM (Fedora et dérivés), noarch.
# Construit par build_rpm.sh à partir de l'arborescence commune (build_deb.sh --stage-only) :
# mêmes fichiers que le paquet Debian.
Name:           openvpn-gui
Version:        %{version}
Release:        1%{?dist}
Summary:        OpenVPN GUI by Dukiwi — client OpenVPN graphique pour NetworkManager
License:        GPL-3.0-or-later
URL:            https://dukiwi.com
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       gtk3
Requires:       gdk-pixbuf2
Requires:       NetworkManager
Requires:       NetworkManager-openvpn
Requires:       openvpn
Requires:       python3-keyring
Requires:       python3-secretstorage
Requires:       iproute
Requires:       libayatana-appindicator-gtk3
Recommends:     gnome-keyring
Recommends:     gnome-shell-extension-appindicator
Recommends:     NetworkManager-openvpn-gnome

%description
Client OpenVPN graphique moderne (GTK3, couleurs Dukiwi) piloté par NetworkManager : un profil par
réseau, serveur défini à la main (hôte, port, protocole, utilisateur, mot de passe) ou import .ovpn,
animation de connexion avec journal détaillé (nmcli, états NetworkManager, sortie OpenVPN), vue du
trafic en direct une fois connecté, identifiants dans le trousseau système, icône dans la barre
système, interface en français et en anglais.
Application créée par Dukiwi SA, Estavayer-le-Lac, Suisse.

%prep
%setup -q

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a tree/. %{buildroot}/

%post
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true; fi
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database /usr/share/applications >/dev/null 2>&1 || true; fi
if command -v restorecon >/dev/null 2>&1; then restorecon -R /opt/openvpn-gui >/dev/null 2>&1 || true; fi

%preun
if [ "$1" = "0" ]; then
    pkill -f "/opt/openvpn-gui/openvpn-gui" >/dev/null 2>&1 || true
fi

%postun
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true; fi
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database /usr/share/applications >/dev/null 2>&1 || true; fi

%files
/opt/openvpn-gui
%{_bindir}/openvpn-gui
%{_datadir}/applications/openvpn-gui.desktop
%{_datadir}/icons/hicolor/scalable/apps/openvpn-gui.svg
%doc %{_datadir}/doc/openvpn-gui

%changelog
* Thu Oct 15 2026 Dukiwi SA <info@dukiwi.com> - %{version}-1
- Premier paquet RPM : mêmes fonctionnalités que le paquet Debian 1.1.0
