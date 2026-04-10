"""Application configuration manager — persists settings to ~/.config/openvpn-gui/settings.json."""
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "openvpn-gui"
CONFIG_FILE = CONFIG_DIR / "settings.json"

_DEFAULTS = {
    "last_selected_profile": None,
    "minimize_to_tray": True,
    "start_minimized": False,
    "profiles_with_saved_creds": [],
}


def _load_raw() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_raw(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get(key: str):
    return _load_raw().get(key, _DEFAULTS.get(key))


def set_value(key: str, value) -> None:
    data = _load_raw()
    data[key] = value
    _save_raw(data)


def load_all() -> dict:
    return {**_DEFAULTS, **_load_raw()}


def save_all(config: dict) -> None:
    _save_raw(config)


def mark_creds_saved(profile_name: str) -> None:
    data = _load_raw()
    saved = set(data.get("profiles_with_saved_creds", []))
    saved.add(profile_name)
    data["profiles_with_saved_creds"] = list(saved)
    _save_raw(data)


def unmark_creds_saved(profile_name: str) -> None:
    data = _load_raw()
    saved = set(data.get("profiles_with_saved_creds", []))
    saved.discard(profile_name)
    data["profiles_with_saved_creds"] = list(saved)
    _save_raw(data)


def has_saved_creds(profile_name: str) -> bool:
    return profile_name in _load_raw().get("profiles_with_saved_creds", [])
