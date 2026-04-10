"""
Secure credential storage using the system keyring (GNOME Keyring / Secret Service).
Credentials are never written to disk in plain text.
"""
import keyring
import keyring.errors

_SERVICE = "openvpn-gui"


def save(profile_name: str, username: str, password: str) -> None:
    """Store credentials for a profile in the system keyring."""
    keyring.set_password(_SERVICE, f"{profile_name}|username", username)
    keyring.set_password(_SERVICE, f"{profile_name}|password", password)


def load(profile_name: str) -> tuple:
    """Return (username, password) for a profile, or ('', '') if not found."""
    username = keyring.get_password(_SERVICE, f"{profile_name}|username") or ""
    password = keyring.get_password(_SERVICE, f"{profile_name}|password") or ""
    return username, password


def delete(profile_name: str) -> None:
    """Remove stored credentials for a profile."""
    for key in (f"{profile_name}|username", f"{profile_name}|password"):
        try:
            keyring.delete_password(_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def has_credentials(profile_name: str) -> bool:
    """Return True if credentials are stored for this profile."""
    return bool(keyring.get_password(_SERVICE, f"{profile_name}|username"))
