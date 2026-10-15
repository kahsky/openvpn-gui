"""
VPN backend — wraps NetworkManager via nmcli.

All blocking nmcli calls are intended to be run in a background thread;
callers must use GLib.idle_add() to update the GTK UI from the results.

Verbose logging: every command the manager runs (and its result) is sent to
the optional logger callback  log(level, message)  so the GUI can show
exactly what is happening.  Passwords are never logged.
"""
import getpass
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

DEFAULT_PORT = 1194
DEFAULT_PROTO = "udp"

# NetworkManager VPN connection states (NMVpnConnectionState)
VPN_STATE_UNKNOWN = 0
VPN_STATE_PREPARE = 1
VPN_STATE_NEED_AUTH = 2
VPN_STATE_CONNECT = 3
VPN_STATE_IP_CONFIG_GET = 4
VPN_STATE_ACTIVATED = 5
VPN_STATE_FAILED = 6
VPN_STATE_DISCONNECTED = 7

_CERT_DIR = Path.home() / ".cert" / "nm-openvpn"

_REMOTE_RE = re.compile(
    r"^(?:\[(?P<v6>[^\]]+)\]|(?P<host>[^:\s]+))"
    r"(?::(?P<port>\d{1,5}))?"
    r"(?::(?P<proto>[A-Za-z0-9-]+))?$"
)


def parse_remote(entry: str) -> Tuple[str, Optional[int], Optional[str]]:
    """'host[:port[:proto]]' (IPv6 in brackets) → (host, port|None, proto|None)."""
    entry = entry.strip()
    m = _REMOTE_RE.match(entry)
    if not m:
        return entry, None, None
    host = m.group("v6") or m.group("host") or ""
    port = int(m.group("port")) if m.group("port") else None
    proto = m.group("proto")
    if proto:
        proto = "tcp" if proto.lower().startswith("tcp") else "udp"
    return host, port, proto


def format_remote(host: str, port: int, proto: str) -> str:
    host = host.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{int(port)}:{proto}"


def parse_vpn_data(data: str) -> Dict[str, str]:
    """
    Parse nmcli's 'key = value, key2 = value2' vpn.data representation.
    Only splits on commas that are followed by a 'key = ' token, so values
    containing commas (multiple remotes) survive.
    """
    result: Dict[str, str] = {}
    data = data.strip()
    if not data:
        return result
    for chunk in re.split(r",\s*(?=[A-Za-z0-9_-]+\s*=\s*)", data):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            result[k.strip()] = v.strip()
    return result


class VPNManager:

    def __init__(self):
        self._log: Optional[Callable[[str, str], None]] = None
        self._connect_proc: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------------ #
    #  Logging                                                             #
    # ------------------------------------------------------------------ #

    def set_logger(self, cb: Optional[Callable[[str, str], None]]) -> None:
        """cb(level, message) — level is 'info' | 'warn' | 'err' | 'ok'."""
        self._log = cb

    def log(self, level: str, message: str) -> None:
        if self._log:
            try:
                self._log(level, message)
            except Exception:
                pass

    def _run(self, cmd: List[str], timeout: int = 30, quiet: bool = False):
        """Run a command, log it, return (rc, stdout, stderr)."""
        if not quiet:
            self.log("info", "$ " + " ".join(shlex.quote(c) for c in cmd))
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            if not quiet:
                self.log("err", f"timed out after {timeout}s")
            return 124, "", "timed out"
        except FileNotFoundError:
            if not quiet:
                self.log("err", f"{cmd[0]}: command not found")
            return 127, "", f"{cmd[0]} not found"
        dt = (time.monotonic() - t0) * 1000
        if not quiet:
            out = (result.stdout.strip() or result.stderr.strip())
            level = "ok" if result.returncode == 0 else "err"
            summary = out.splitlines()[0] if out else ""
            self.log(level, f"→ exit {result.returncode} ({dt:.0f} ms) {summary}")
        return result.returncode, result.stdout, result.stderr

    # ------------------------------------------------------------------ #
    #  Import / create / delete                                            #
    # ------------------------------------------------------------------ #

    def import_config(self, filepath: str) -> Tuple[bool, str]:
        """Import an .ovpn file into NetworkManager. Returns (ok, name_or_error)."""
        if not os.path.isfile(filepath):
            return False, "File not found"
        rc, stdout, stderr = self._run(
            ["nmcli", "connection", "import", "type", "openvpn", "file", filepath]
        )
        if rc == 127:
            return False, "nmcli not found — is NetworkManager installed?"
        if rc == 0:
            output = stdout.strip()
            # nmcli prints: Connection 'name' (uuid) successfully added.
            if "'" in output:
                name = output.split("'")[1]
            else:
                name = os.path.splitext(os.path.basename(filepath))[0]
            self.set_owner(name)
            return True, name
        err = stderr.strip() or stdout.strip()
        return False, err or "Failed to import config"

    @staticmethod
    def _owner() -> str:
        try:
            return getpass.getuser()
        except Exception:
            return ""

    def set_owner(self, profile_name: str) -> bool:
        """
        Restrict the profile to the current user (connection.permissions).
        A user-owned profile only needs the 'modify.own' polkit permission, so later
        edits (host, port, username, cached secrets) never ask for an admin password —
        this matters on Fedora, where system-wide changes require authentication.
        """
        user = self._owner()
        if not user:
            return False
        rc, _, _ = self._run(
            ["nmcli", "connection", "modify", profile_name, "connection.permissions", f"user:{user}"]
        )
        return rc == 0

    def create_manual_profile(
        self,
        name: str,
        host: str,
        port: int,
        proto: str = DEFAULT_PROTO,
        ca_path: str = "",
        username: str = "",
    ) -> Tuple[bool, str]:
        """
        Create an OpenVPN profile from scratch (password authentication).
        The CA certificate (if given) is copied to ~/.cert/nm-openvpn/ like
        nmcli's own importer does.  Returns (ok, name_or_error).
        """
        name = name.strip()
        host = host.strip()
        if not name:
            return False, "Profile name is required"
        if not host:
            return False, "Host is required"
        if not (1 <= int(port) <= 65535):
            return False, "Port must be between 1 and 65535"
        proto = "tcp" if str(proto).lower().startswith("tcp") else "udp"

        data = {
            "connection-type": "password",
            "remote": format_remote(host, port, proto),
            "port": str(int(port)),
            "proto-tcp": "yes" if proto == "tcp" else "no",
            "dev": "tun",
            "password-flags": "1",
            "remote-cert-tls": "server",
        }
        if username.strip():
            data["username"] = username.strip()

        if ca_path:
            if not os.path.isfile(ca_path):
                return False, f"CA certificate not found: {ca_path}"
            try:
                _CERT_DIR.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
                dest = _CERT_DIR / f"{safe}-ca.pem"
                shutil.copyfile(ca_path, dest)
                os.chmod(dest, 0o600)
                data["ca"] = str(dest)
                self.log("info", f"CA certificate copied to {dest}")
            except OSError as exc:
                return False, f"Could not copy CA certificate: {exc}"

        vpn_data = ", ".join(f"{k}={v}" for k, v in data.items())
        cmd = [
            "nmcli", "connection", "add", "type", "vpn", "vpn-type", "openvpn",
            "con-name", name, "connection.autoconnect", "no",
        ]
        if self._owner():
            # user-owned profile: creatable and editable with 'modify.own' only (no admin prompt)
            cmd += ["connection.permissions", f"user:{self._owner()}"]
        cmd += ["vpn.data", vpn_data]
        rc, stdout, stderr = self._run(cmd)
        if rc == 0:
            return True, name
        return False, (stderr.strip() or stdout.strip() or "Failed to create profile")

    def delete_profile(self, profile_name: str) -> Tuple[bool, str]:
        """Remove a VPN profile from NetworkManager."""
        rc, stdout, stderr = self._run(["nmcli", "connection", "delete", profile_name])
        if rc == 0:
            return True, "Profile deleted"
        return False, stderr.strip() or "Failed to delete"

    # ------------------------------------------------------------------ #
    #  Profile settings (host / port / protocol / username)                #
    # ------------------------------------------------------------------ #

    def get_profile_details(self, profile_name: str) -> Dict:
        """
        Return the editable server settings of a profile:
          { host, port, proto, username, conn_type, ca, remotes (list) }
        """
        details = {
            "host": "", "port": DEFAULT_PORT, "proto": DEFAULT_PROTO,
            "username": "", "conn_type": "", "ca": "", "remotes": [],
        }
        rc, stdout, _ = self._run(
            ["nmcli", "-t", "-f", "vpn.data", "connection", "show", profile_name],
            timeout=10, quiet=True,
        )
        if rc != 0:
            return details
        raw = ""
        for line in stdout.splitlines():
            if line.startswith("vpn.data:"):
                raw = line.split(":", 1)[1]
                break
        data = parse_vpn_data(raw)
        details["username"] = data.get("username", "")
        details["conn_type"] = data.get("connection-type", "")
        details["ca"] = data.get("ca", "")

        default_port = DEFAULT_PORT
        if data.get("port", "").isdigit():
            default_port = int(data["port"])
        default_proto = "tcp" if data.get("proto-tcp", "").lower() == "yes" else "udp"

        remotes = [r for r in re.split(r"[,\s]+", data.get("remote", "")) if r]
        details["remotes"] = remotes
        if remotes:
            host, port, proto = parse_remote(remotes[0])
            details["host"] = host
            details["port"] = port or default_port
            details["proto"] = proto or default_proto
        else:
            details["port"] = default_port
            details["proto"] = default_proto
        return details

    def set_remote(
        self, profile_name: str, host: str, port: int, proto: str = DEFAULT_PROTO
    ) -> Tuple[bool, str]:
        """Persist host / port / protocol into the NetworkManager profile."""
        host = host.strip()
        if not host or any(c.isspace() for c in host):
            return False, "Invalid host"
        try:
            port = int(port)
        except (TypeError, ValueError):
            return False, "Invalid port"
        if not (1 <= port <= 65535):
            return False, "Port must be between 1 and 65535"
        proto = "tcp" if str(proto).lower().startswith("tcp") else "udp"

        rc, stdout, stderr = self._run(
            [
                "nmcli", "connection", "modify", profile_name,
                "+vpn.data", f"remote={format_remote(host, port, proto)}",
                "+vpn.data", f"port={port}",
                "+vpn.data", f"proto-tcp={'yes' if proto == 'tcp' else 'no'}",
            ]
        )
        if rc == 0:
            return True, "Server settings saved"
        return False, stderr.strip() or stdout.strip() or "Failed to save server settings"

    def set_username(self, profile_name: str, username: str) -> Tuple[bool, str]:
        """Persist the username into the profile (vpn.data username=...)."""
        username = username.strip()
        if username:
            args = ["+vpn.data", f"username={username}"]
        else:
            args = ["-vpn.data", "username"]
        rc, stdout, stderr = self._run(
            ["nmcli", "connection", "modify", profile_name] + args
        )
        if rc == 0:
            return True, "Username saved"
        # Removing a key that doesn't exist is not an error for us
        if not username:
            return True, ""
        return False, stderr.strip() or stdout.strip() or "Failed to save username"

    # ------------------------------------------------------------------ #
    #  Connect / disconnect                                                #
    # ------------------------------------------------------------------ #

    def clear_secrets(self, profile_name: str) -> bool:
        """
        Ask NetworkManager to forget the secrets it caches in memory for this
        profile (D-Bus Settings.Connection.ClearSecrets).  Without this, NM
        silently reuses the password of the previous successful connection and
        ignores the one typed in the GUI.
        """
        rc, stdout, _ = self._run(
            ["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"], timeout=10, quiet=True,
        )
        uuid = ""
        for line in stdout.splitlines():
            name, _, u = line.rpartition(":")
            if name == profile_name:
                uuid = u.strip()
                break
        if rc != 0 or not uuid:
            return False
        try:
            import gi
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            res = bus.call_sync(
                "org.freedesktop.NetworkManager",
                "/org/freedesktop/NetworkManager/Settings",
                "org.freedesktop.NetworkManager.Settings",
                "GetConnectionByUuid",
                GLib.Variant("(s)", (uuid,)),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE, 5000, None,
            )
            path = res.unpack()[0]
            bus.call_sync(
                "org.freedesktop.NetworkManager", path,
                "org.freedesktop.NetworkManager.Settings.Connection",
                "ClearSecrets", None, None,
                Gio.DBusCallFlags.NONE, 5000, None,
            )
            self.log("info", f"D-Bus {path} ClearSecrets() → cached secrets dropped, "
                             "the password you typed will be used")
            return True
        except Exception as exc:
            self.log("warn", f"ClearSecrets failed ({exc}); NetworkManager may reuse a cached password")
            return False

    def connect(
        self, profile_name: str, username: str = "", password: str = "",
        clear_cached_secrets: bool = True,
    ) -> Tuple[bool, str]:
        """
        Connect to a VPN profile.

        Credentials are piped via stdin to nmcli so they are never written
        to disk.  Returns (ok, message).
        """
        cmd = ["nmcli", "--wait", "60", "connection", "up", profile_name]
        try:
            if username or password:
                if clear_cached_secrets:
                    self.clear_secrets(profile_name)
                creds = (
                    f"vpn.secrets.username:{username}\n"
                    f"vpn.secrets.password:{password}\n"
                )
                cmd += ["passwd-file", "/dev/stdin"]
                self.log("info", "$ " + " ".join(shlex.quote(c) for c in cmd)
                         + "   (credentials piped on stdin, never written to disk)")
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._connect_proc = proc
                stdout, stderr = proc.communicate(input=creds.encode(), timeout=65)
                rc = proc.returncode
                out = stderr.decode().strip() or stdout.decode().strip()
            else:
                self.log("info", "$ " + " ".join(shlex.quote(c) for c in cmd))
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                self._connect_proc = proc
                stdout, stderr = proc.communicate(timeout=65)
                rc = proc.returncode
                out = stderr.decode().strip() or stdout.decode().strip()

            self._connect_proc = None
            if rc == 0:
                self.log("ok", f"→ exit 0: {out or 'Connection activated'}")
                return True, "Connected"
            self.log("err", f"→ exit {rc}: {out or 'Connection failed'}")
            return False, out or "Connection failed"
        except subprocess.TimeoutExpired:
            self._connect_proc = None
            self.log("err", "→ nmcli did not return within 65 s")
            return False, "Connection timed out after 60 s"
        except FileNotFoundError:
            self._connect_proc = None
            return False, "nmcli not found — is NetworkManager installed?"
        except Exception as exc:
            self._connect_proc = None
            return False, str(exc)

    def disconnect(self, profile_name: str) -> Tuple[bool, str]:
        """Disconnect an active VPN profile (also cancels a pending connect)."""
        rc, stdout, stderr = self._run(["nmcli", "connection", "down", profile_name])
        if rc == 0:
            return True, "Disconnected"
        return False, stderr.strip() or "Failed to disconnect"

    # ------------------------------------------------------------------ #
    #  Status / listing                                                    #
    # ------------------------------------------------------------------ #

    def get_profiles(self) -> List[Dict]:
        """
        Return all VPN profiles known to NetworkManager as a list of dicts:
          { name, uuid, connected }
        """
        rc, stdout, _ = self._run(
            ["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"],
            timeout=10, quiet=True,
        )
        if rc != 0:
            return []
        active = self._active_vpn_names()
        profiles: List[Dict] = []
        for line in stdout.splitlines():
            # Lines look like:  My VPN:some-uuid:vpn  (use rsplit: names may contain ':')
            parts = line.rsplit(":", 2)
            if len(parts) == 3 and "vpn" in parts[2].lower():
                profiles.append(
                    {"name": parts[0], "uuid": parts[1], "connected": parts[0] in active}
                )
        return profiles

    def _active_vpn_names(self) -> set:
        """Names of currently-active (fully activated) VPN connections."""
        rc, stdout, _ = self._run(
            ["nmcli", "-t", "-f", "NAME,TYPE,STATE", "connection", "show", "--active"],
            timeout=10, quiet=True,
        )
        names: set = set()
        if rc != 0:
            return names
        for line in stdout.splitlines():
            parts = line.rsplit(":", 2)
            if len(parts) == 3 and "vpn" in parts[1].lower():
                if parts[2].strip().lower() in ("activated", ""):
                    names.add(parts[0])
        return names

    def is_connected(self, profile_name: str) -> bool:
        return profile_name in self._active_vpn_names()

    def get_server(self, profile_name: str) -> str:
        """'host:port' of the primary remote (for list rows)."""
        d = self.get_profile_details(profile_name)
        if not d["host"]:
            return ""
        return f"{d['host']}:{d['port']}"

    def get_active_info(self, profile_name: str) -> Dict:
        """
        Details of an active (or activating) VPN connection:
          { active, state, vpn_state(int), vpn_state_text, ip4, ip6, gateway,
            dns[], banner, username, iface }
        """
        info = {
            "active": False, "state": "", "vpn_state": -1, "vpn_state_text": "",
            "ip4": "", "ip6": "", "gateway": "", "dns": [], "banner": "",
            "username": "", "iface": "",
        }
        rc, stdout, _ = self._run(
            ["nmcli", "-t", "connection", "show", "--active", profile_name],
            timeout=10, quiet=True,
        )
        if rc != 0 or not stdout.strip():
            return info
        for line in stdout.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key == "GENERAL.STATE":
                info["state"] = val
                info["active"] = True
            elif key == "VPN.VPN-STATE":
                info["vpn_state_text"] = val
                m = re.match(r"(\d+)", val)
                if m:
                    info["vpn_state"] = int(m.group(1))
            elif key == "IP4.ADDRESS[1]":
                info["ip4"] = val
            elif key == "IP6.ADDRESS[1]":
                info["ip6"] = val
            elif key == "VPN.GATEWAY":
                info["gateway"] = val
            elif key == "VPN.BANNER":
                info["banner"] = val if val != "--" else ""
            elif key == "VPN.USERNAME":
                info["username"] = val
            elif key.startswith("IP4.DNS["):
                info["dns"].append(val)
        if info["ip4"]:
            info["iface"] = self.find_iface_for_ip(info["ip4"].split("/")[0])
        if not info["iface"]:
            info["iface"] = self._guess_tun_iface()
        return info

    def get_vpn_state(self, profile_name: str) -> int:
        """NMVpnConnectionState of the profile, or -1 when not active."""
        return self.get_active_info(profile_name)["vpn_state"]

    def get_activation_timestamp(self, profile_name: str) -> int:
        """Unix time of the last successful activation (0 if unknown)."""
        rc, stdout, _ = self._run(
            ["nmcli", "-g", "connection.timestamp", "connection", "show", profile_name],
            timeout=10, quiet=True,
        )
        if rc == 0 and stdout.strip().isdigit():
            return int(stdout.strip())
        return 0

    # ------------------------------------------------------------------ #
    #  Interfaces / traffic counters                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def find_iface_for_ip(ip: str) -> str:
        """Find the network interface carrying the given IPv4 address."""
        if not ip:
            return ""
        try:
            result = subprocess.run(
                ["ip", "-o", "-4", "addr", "show"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                # "5: tun0    inet 10.8.0.6/24 scope global tun0\ ..."
                if len(parts) >= 4 and parts[2] == "inet":
                    if parts[3].split("/")[0] == ip:
                        return parts[1]
        except Exception:
            pass
        # Fallback: sysfs has no addresses; try /proc/net/fib_trie is overkill
        return ""

    @staticmethod
    def _guess_tun_iface() -> str:
        try:
            cands = sorted(
                n for n in os.listdir("/sys/class/net")
                if n.startswith(("tun", "tap", "ovpn"))
            )
        except OSError:
            return ""
        for n in cands:
            try:
                with open(f"/sys/class/net/{n}/operstate") as f:
                    if f.read().strip() in ("up", "unknown"):
                        return n
            except OSError:
                continue
        return cands[0] if cands else ""

    @staticmethod
    def read_iface_counters(iface: str) -> Tuple[int, int]:
        """(rx_bytes, tx_bytes) of an interface, from sysfs. (0, 0) if gone."""
        base = f"/sys/class/net/{iface}/statistics/"
        try:
            with open(base + "rx_bytes") as f:
                rx = int(f.read().strip())
            with open(base + "tx_bytes") as f:
                tx = int(f.read().strip())
            return rx, tx
        except (OSError, ValueError):
            return 0, 0
