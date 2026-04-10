# OpenVPN GUI

A modern, secure, GTK3-based OpenVPN client for Linux Mint 22.x / Ubuntu 24.x.

## Features

- **System tray icon** — green shield when connected, gray when disconnected
- **One-click import** — browse for `.ovpn` config files
- **Secure credentials** — username & password stored in GNOME Keyring (never plain text on disk)
- **Multiple profiles** — manage as many VPN profiles as you need
- **NetworkManager integration** — uses `nmcli` under the hood; no root password prompts
- **Live status polling** — tray icon and connection status update automatically
- **Minimize to tray** — close the window to keep it running in the system tray

## Layout

```
┌─ OpenVPN GUI ─────────────────────────────────────────────────────────┐
│ VPN PROFILES        │  WorkVPN                                  [🗑]  │
│ ─────────────────   │  vpn.company.com          ● Connected           │
│ ● WorkVPN           │  ──────────────────────────────────────         │
│ ○ HomeVPN           │  USERNAME  [john.doe                    ]       │
│ ○ Lab               │  PASSWORD  [••••••••••••••••            👁]     │
│                     │  ☑ Remember credentials (system keyring)        │
│ [+ Import Config]   │  ──────────────────────────────────────         │
│                     │  [              DISCONNECT              ]       │
└─────────────────────┴─────────────────────────────────────────────────┘
```

## Requirements

| Component | Version |
|---|---|
| Linux Mint | 21.x / 22.x |
| Ubuntu | 22.04 / 24.04 |
| Python | 3.10+ |
| NetworkManager | any recent |

---

## Installation (recommended — via .deb)

### Method 1 — download the pre-built package

```bash
# Download the latest release
wget https://dukiwi.com/repo/openvpn-gui/openvpn-gui_1.0.1_all.deb

# Install (apt resolves all dependencies automatically)
sudo apt install ./openvpn-gui_1.0.1_all.deb
```

> **All packages directory:** https://dukiwi.com/repo/index.php?path=openvpn-gui

### Method 2 — build the .deb yourself from source

```bash
git clone https://github.com/kahsky/openvpn-gui.git
cd openvpn-gui

# Build the .deb (no root required)
./build_deb.sh

# Install (apt handles all dependencies)
sudo apt install ./build/openvpn-gui_1.0.1_all.deb
```

Or build and install in one step:

```bash
./build_deb.sh --install
```

### Uninstall

```bash
sudo apt remove openvpn-gui
# Full purge (removes config too):
sudo apt purge openvpn-gui
```

---

## Running without installing

```bash
# Install system deps
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
     network-manager-openvpn gir1.2-ayatanaappindicator3-0.1 \
     python3-keyring python3-secretstorage

# Run directly
./openvpn-gui
```

---

## Usage

1. **Import a config** — click "+ Import Config" or the folder icon in the header bar, then select your `.ovpn` file.
2. **Enter credentials** — type your username and password. Tick "Remember credentials" to save them securely in the system keyring.
3. **Connect** — click **CONNECT**. The tray icon turns green when the tunnel is up.
4. **Disconnect** — click **DISCONNECT** or right-click the tray icon → Disconnect.

---

## Architecture

```
openvpn_gui/
├── main.py         — Entry point
├── app.py          — Gtk.Application subclass
├── window.py       — Main GTK3 window (two-panel layout + CSS)
├── tray.py         — AppIndicator3 / GtkStatusIcon tray icon
├── vpn_manager.py  — nmcli wrapper (connect / disconnect / import)
├── credentials.py  — keyring wrapper (GNOME Keyring / Secret Service)
└── config.py       — JSON settings in ~/.config/openvpn-gui/

assets/
├── icon_connected.svg      — Green shield  (tray: VPN up)
├── icon_disconnected.svg   — Gray shield   (tray: VPN down)
└── icon_app.svg            — Blue shield   (app / taskbar)
```

**Build script:**

```
build_deb.sh  — builds a self-contained .deb with all metadata
                works as regular user (fakeroot) or as root
```

---

## Security notes

- Credentials are stored **exclusively** in the system keyring (libsecret / GNOME Keyring).
- When connecting, the password is piped to `nmcli` via **stdin** — it is never written to disk or to a temp file.
- VPN profiles are managed by NetworkManager, stored in `/etc/NetworkManager/system-connections/` with root-only read permissions.

---

## Releases

Pre-built `.deb` packages are available at:
**https://dukiwi.com/repo/index.php?path=openvpn-gui**

| Version | Download |
|---|---|
| 1.0.1 | [openvpn-gui_1.0.1_all.deb](https://dukiwi.com/repo/openvpn-gui/openvpn-gui_1.0.1_all.deb) |

---

## License

GNU General Public License v3 — see [LICENSE](LICENSE).
