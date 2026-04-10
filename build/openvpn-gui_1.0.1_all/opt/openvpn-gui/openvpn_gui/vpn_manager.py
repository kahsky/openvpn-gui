"""
VPN backend — wraps NetworkManager via nmcli.

All blocking nmcli calls are intended to be run in a background thread;
callers must use GLib.idle_add() to update the GTK UI from the results.
"""
import subprocess
import os
from typing import List, Dict, Tuple


class VPNManager:

    # ------------------------------------------------------------------ #
    #  Import / delete                                                     #
    # ------------------------------------------------------------------ #

    def import_config(self, filepath: str) -> Tuple[bool, str]:
        """Import an .ovpn file into NetworkManager. Returns (ok, name_or_error)."""
        if not os.path.isfile(filepath):
            return False, "File not found"
        try:
            result = subprocess.run(
                ["nmcli", "connection", "import", "type", "openvpn", "file", filepath],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                # nmcli prints: Connection 'name' (uuid) successfully added.
                if "'" in output:
                    name = output.split("'")[1]
                    return True, name
                return True, os.path.splitext(os.path.basename(filepath))[0]
            err = result.stderr.strip() or result.stdout.strip()
            return False, err or "Failed to import config"
        except subprocess.TimeoutExpired:
            return False, "Import timed out"
        except FileNotFoundError:
            return False, "nmcli not found — is NetworkManager installed?"
        except Exception as exc:
            return False, str(exc)

    def delete_profile(self, profile_name: str) -> Tuple[bool, str]:
        """Remove a VPN profile from NetworkManager."""
        try:
            result = subprocess.run(
                ["nmcli", "connection", "delete", profile_name],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "Profile deleted"
            return False, result.stderr.strip() or "Failed to delete"
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------ #
    #  Connect / disconnect                                                #
    # ------------------------------------------------------------------ #

    def connect(
        self, profile_name: str, username: str = "", password: str = ""
    ) -> Tuple[bool, str]:
        """
        Connect to a VPN profile.

        Credentials are piped via stdin to nmcli so they are never written
        to disk.  Returns (ok, message).
        """
        cmd = ["nmcli", "--wait", "60", "connection", "up", profile_name]
        try:
            if username or password:
                creds = (
                    f"vpn.secrets.username:{username}\n"
                    f"vpn.secrets.password:{password}\n"
                )
                cmd += ["passwd-file", "/dev/stdin"]
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = proc.communicate(
                    input=creds.encode(), timeout=65
                )
                rc = proc.returncode
                out = stderr.decode().strip() or stdout.decode().strip()
            else:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=65
                )
                rc = result.returncode
                out = result.stderr.strip() or result.stdout.strip()

            if rc == 0:
                return True, "Connected"
            return False, out or "Connection failed"
        except subprocess.TimeoutExpired:
            return False, "Connection timed out after 60 s"
        except FileNotFoundError:
            return False, "nmcli not found — is NetworkManager installed?"
        except Exception as exc:
            return False, str(exc)

    def disconnect(self, profile_name: str) -> Tuple[bool, str]:
        """Disconnect an active VPN profile."""
        try:
            result = subprocess.run(
                ["nmcli", "connection", "down", profile_name],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "Disconnected"
            return False, result.stderr.strip() or "Failed to disconnect"
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------ #
    #  Status / listing                                                    #
    # ------------------------------------------------------------------ #

    def get_profiles(self) -> List[Dict]:
        """
        Return all OpenVPN profiles known to NetworkManager as a list of dicts:
          { name, uuid, connected }
        """
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            active = self._active_vpn_names()
            profiles: List[Dict] = []

            for line in result.stdout.splitlines():
                # Lines look like:  My VPN:some-uuid:vpn
                # UUID has hyphens; TYPE contains "vpn"
                # Use rsplit to handle colons in names
                parts = line.rsplit(":", 2)
                if len(parts) == 3 and "vpn" in parts[2].lower():
                    profiles.append(
                        {
                            "name": parts[0],
                            "uuid": parts[1],
                            "connected": parts[0] in active,
                        }
                    )
            return profiles
        except Exception:
            return []

    def _active_vpn_names(self) -> set:
        """Return a set of names of currently-active VPN connections."""
        try:
            result = subprocess.run(
                [
                    "nmcli", "-t", "-f", "NAME,TYPE,STATE",
                    "connection", "show", "--active",
                ],
                capture_output=True, text=True, timeout=10,
            )
            names: set = set()
            for line in result.stdout.splitlines():
                parts = line.rsplit(":", 2)
                if len(parts) == 3 and "vpn" in parts[1].lower():
                    names.add(parts[0])
            return names
        except Exception:
            return set()

    def is_connected(self, profile_name: str) -> bool:
        return profile_name in self._active_vpn_names()

    def get_server(self, profile_name: str) -> str:
        """Try to extract the remote server from the NM connection data."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "vpn.data", "connection", "show", profile_name],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if "vpn.data:" in line:
                    data = line.split("vpn.data:", 1)[1]
                    for part in data.split(","):
                        part = part.strip()
                        if part.startswith("remote ="):
                            return part.split("=", 1)[1].strip()
        except Exception:
            pass
        return ""
