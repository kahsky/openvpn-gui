# OpenVPN GUI — by Dukiwi

A modern, secure, GTK3-based OpenVPN client for **Linux Mint 22** and **Ubuntu 24.04+**,
created by **[Dukiwi](https://dukiwi.com)** and styled in Dukiwi blue (`#013861`).
Define the server yourself (host, port, user, password), watch a live traffic view once connected,
and follow exactly what happens during the connection with the verbose log.

![OpenVPN GUI by Dukiwi — settings, connection animation with verbose log, live traffic view](https://www.dukiwi.com/repo/openvpn-gui/openvpn-gui.png?v=92732302)

## Installation

### Linux Mint 22 and Ubuntu 24.04+ (signed Dukiwi APT repository, automatic updates)

The `noble` suite serves all these versions. It is the same Dukiwi repository as
[ClamAV Antivirus GUI](https://github.com/kahsky/clamav-antivirus): if you already added it,
`sudo apt install openvpn-gui` is enough.

```bash
sudo mkdir -p /usr/share/keyrings
curl -fsSL https://www.dukiwi.com/repo/apt/dukiwi-clamav.gpg | sudo tee /usr/share/keyrings/dukiwi-clamav.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/dukiwi-clamav.gpg] https://www.dukiwi.com/repo/apt noble main" | sudo tee /etc/apt/sources.list.d/dukiwi-clamav.list
sudo apt update && sudo apt install -y openvpn-gui
```

Updates then arrive through the Mint Update Manager or Ubuntu Software, like any other package.

### Direct download

- Mint / Ubuntu: [openvpn-gui_1.1.0_all.deb](https://www.dukiwi.com/repo/openvpn-gui/openvpn-gui_1.1.0_all.deb)
- All versions: [www.dukiwi.com/repo/openvpn-gui](https://www.dukiwi.com/repo/index.php?path=openvpn-gui)

### Install a downloaded package by hand

```bash
sudo apt install ./openvpn-gui_1.1.0_all.deb     # apt resolves all dependencies
```

### Build the .deb yourself from source

```bash
git clone https://github.com/kahsky/openvpn-gui.git
cd openvpn-gui
./build_deb.sh              # no root required (fakeroot)
sudo apt install ./build/openvpn-gui_1.1.0_all.deb
# or build and install in one step:
./build_deb.sh --install
```

### Uninstall

```bash
sudo apt remove openvpn-gui
sudo apt purge openvpn-gui      # also removes the configuration
```

---

## Features

- **Manual server definition** — set the **host**, **port** (OpenVPN default `1194`, changeable),
  **protocol** (UDP/TCP), **username** and **password** yourself, either on an imported profile
  or from scratch with *✎ Manual profile* (no `.ovpn` file needed, CA certificate optional).
- **Live traffic view** — once connected: download / upload rates, 90-second sparkline graph,
  session totals, peak rates, tunnel IP, interface, gateway, DNS and connection duration.
- **Connection animation + "See more"** — sonar/comet animation with a 4-step progress line
  (Preparing → Authenticating → Establishing tunnel → Configuring network). *See more* reveals a
  **verbose log** showing exactly what happens: every `nmcli` command, NetworkManager VPN states and
  the live NetworkManager / OpenVPN journal output. Copy-to-clipboard for support tickets.
- **Cancel** a connection in progress; failures show an inline error with a *Details* button, and a
  wrong password is reported immediately (`AUTH_FAILED`) instead of after NetworkManager's 60 s timeout.
- **One-click import** — browse for `.ovpn` config files.
- **Secure credentials** — username & password stored in GNOME Keyring (never plain text on disk).
- **Multiple profiles** — manage as many VPN profiles as you need.
- **NetworkManager integration** — uses `nmcli` under the hood; no root password prompts.
- **System tray icon** — blue shield when connected, pulsing navy while connecting, grey when disconnected.
- **Minimize to tray**, **English / French** interface (follows your locale).

## Layout

```
┌─ OpenVPN GUI · by Dukiwi ──────────────────────────────────────────────────┐
│ VPN PROFILES        │  WorkVPN                                        [🗑]  │
│ ─────────────────   │  vpn.company.com:1194 · UDP       ● Connected        │
│ ● WorkVPN           │  ───────────────────────────────────────────         │
│ ○ HomeVPN           │  ● Connected 00:12:34  IP 10.8.0.6  tun0  via …      │
│ ○ Lab               │  ┌──────────────────────────────────────────┐        │
│                     │  │ ↓ DOWNLOAD 1.2 MB/s     ↑ UPLOAD 120 KB/s │        │
│ [+ Import .ovpn]    │  │ ▁▂▃▅▇█▇▅▃▂▁▂▃▅▇  (live graph)             │        │
│ [✎ Manual profile]  │  │ Received 45.2 MB · Sent 3.1 MB            │        │
│                     │  └──────────────────────────────────────────┘        │
│ DUKIWI      v1.1.0  │  [See more ▾]  → verbose log                         │
│                     │  [               DISCONNECT               ]          │
└─────────────────────┴──────────────────────────────────────────────────────┘
```

Disconnected, the right panel shows the editable **SERVER** block (host / port / protocol) and
the **CREDENTIALS** block (username / password / remember). Changes are written to the
NetworkManager profile when you leave a field or press **CONNECT**.

## Requirements

| Component | Version |
|---|---|
| Linux Mint | 21.x / 22.x |
| Ubuntu | 22.04 / 24.04 / 26.04 |
| Python | 3.10+ |
| NetworkManager + network-manager-openvpn | any recent |

> The verbose log reads the system journal. To see NetworkManager / OpenVPN lines your user must
> be in the `adm` or `systemd-journal` group (default for the first user on Mint/Ubuntu).

---

## Running without installing

```bash
# Install system deps
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
     network-manager-openvpn gir1.2-ayatanaappindicator3-0.1 \
     python3-keyring python3-secretstorage iproute2

# Run directly
./openvpn-gui
```

---

## Usage

1. **Add a profile** — click *+ Import .ovpn* and pick your file, **or** click *✎ Manual profile*
   and type the host, port (1194 by default), protocol, optional CA certificate, username and password.
2. **Adjust the server** — on any profile you can edit host / port / protocol; the change is saved to
   NetworkManager when you leave the field or connect.
3. **Enter credentials** — type your username and password. Tick *Remember credentials* to save
   them securely in the system keyring.
4. **Connect** — click **CONNECT**. Watch the animation; click **See more** to follow the verbose
   log (nmcli commands, NetworkManager states, OpenVPN output). **CANCEL** aborts.
5. **Monitor** — once connected the panel shows live download/upload rates, the traffic graph,
   totals, tunnel IP and duration. **See more** keeps the log available.
6. **Disconnect** — click **DISCONNECT** or right-click the tray icon → *Disconnect*.

---

## Architecture

```
openvpn_gui/
├── main.py         — Entry point
├── app.py          — Gtk.Application subclass
├── window.py       — Main window: sidebar + form / connecting / connected views + verbose log
├── widgets.py      — Cairo widgets: ConnectAnimation, StepIndicator, TrafficGraph, LogView, LogoWidget
├── dialogs.py      — Manual profile dialog, About box (Dukiwi)
├── monitor.py      — JournalTail (journalctl -f), VpnStatePoller, TrafficSampler (sysfs counters)
├── theme.py        — Dukiwi palette (#013861) + GTK CSS
├── i18n.py         — English / French strings
├── tray.py         — AppIndicator3 / GtkStatusIcon tray icon
├── vpn_manager.py  — nmcli wrapper (import / create / modify / connect / disconnect / active info)
├── credentials.py  — keyring wrapper (GNOME Keyring / Secret Service)
└── config.py       — JSON settings in ~/.config/openvpn-gui/

assets/
├── icon_app.svg            — Dukiwi navy shield (app / taskbar)
├── icon_connected.svg      — Bright blue shield with check (tray: VPN up)
├── icon_connecting.svg     — Navy shield with dots (tray: connecting)
├── icon_disconnected.svg   — Grey shield (tray: VPN down)
└── logo_dukiwi.png         — Dukiwi word-mark (sidebar footer, About box)

openvpn-gui.png   — README hero image (served from https://www.dukiwi.com/repo/openvpn-gui/)
build_deb.sh      — builds a self-contained .deb (fakeroot or root)
```

---

## How it works under the hood

| Action | Command run (visible in the verbose log) |
|---|---|
| Import | `nmcli connection import type openvpn file X.ovpn` |
| Manual profile | `nmcli connection add type vpn vpn-type openvpn con-name NAME vpn.data "connection-type=password, remote=HOST:PORT:PROTO, …"` |
| Change host/port | `nmcli connection modify NAME +vpn.data "remote=HOST:PORT:PROTO" +vpn.data "port=PORT" +vpn.data "proto-tcp=yes/no"` |
| Connect | D-Bus `Settings.Connection.ClearSecrets`, then `nmcli --wait 60 connection up NAME passwd-file /dev/stdin` (secrets piped on stdin) |
| Progress | `nmcli -t connection show --active NAME` (VPN.VPN-STATE) + `journalctl -f` (NetworkManager, nm-openvpn) |
| Traffic | `/sys/class/net/tunX/statistics/{rx,tx}_bytes`, sampled every second |
| Disconnect / cancel | `nmcli connection down NAME` |

## Security notes

- Credentials are stored **exclusively** in the system keyring (libsecret / GNOME Keyring).
- When connecting, the password is piped to `nmcli` via **stdin** — it is never written to disk,
  to a temp file, or to the verbose log. NetworkManager's cached copy of a previous password is
  cleared first, so the password you typed is the one used.
- VPN profiles are managed by NetworkManager, stored in `/etc/NetworkManager/system-connections/`
  with root-only read permissions. CA certificates of manual profiles are copied to
  `~/.cert/nm-openvpn/` (mode 600), like nmcli's own importer does.
- Packages are signed: the APT repository index is signed with the Dukiwi key, and each `.deb` in
  the repository comes with a `.sha256` file and a signed `manifest.json`.

---

## Releases

Pre-built `.deb` packages are available at:
**https://www.dukiwi.com/repo/index.php?path=openvpn-gui**

| Version | Download | Highlights |
|---|---|---|
| 1.1.0 | [openvpn-gui_1.1.0_all.deb](https://www.dukiwi.com/repo/openvpn-gui/openvpn-gui_1.1.0_all.deb) | Manual host/port/user/password, live traffic view, connection animation + verbose log, Dukiwi theme, French UI, APT repository |
| 1.0.1 | [openvpn-gui_1.0.1_all.deb](https://www.dukiwi.com/repo/openvpn-gui/openvpn-gui_1.0.1_all.deb) | Initial release |

---

## Credits & License

Application created by **Dukiwi** — https://dukiwi.com

GNU General Public License v3 — see [LICENSE](LICENSE).
