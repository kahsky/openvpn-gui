"""
System tray icon.

Tries AppIndicator3 / AyatanaAppIndicator3 first (native Ubuntu/Mint style).
Falls back to the deprecated-but-functional Gtk.StatusIcon for compatibility.
"""
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# Resolve asset paths relative to this package
_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)
ICON_CONNECTED = os.path.join(_ASSETS, "icon_connected.svg")
ICON_DISCONNECTED = os.path.join(_ASSETS, "icon_disconnected.svg")

# ── Try loading AppIndicator3 (preferred) ─────────────────────────────────── #
_AppIndicator3 = None
_IndicatorStatus = None
_IndicatorCategory = None

for _mod_name in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(_mod_name, "0.1")
        from gi.repository import AyatanaAppIndicator3 as _mod  # type: ignore
        _AppIndicator3 = _mod
        break
    except (ValueError, ImportError):
        try:
            from gi.repository import AppIndicator3 as _mod  # type: ignore
            _AppIndicator3 = _mod
            break
        except (ValueError, ImportError):
            pass


class TrayIcon:
    """Manages the system tray icon and its context menu."""

    def __init__(self, on_show: callable, on_quit: callable):
        self._on_show = on_show
        self._on_quit = on_quit
        self._connected = False
        self._active_profile = ""
        self._connect_toggle_cb = None

        if _AppIndicator3:
            self._use_indicator = True
            self._setup_indicator()
        else:
            self._use_indicator = False
            self._setup_status_icon()

    # ── Setup ──────────────────────────────────────────────────────────────── #

    def _setup_indicator(self):
        self._ind = _AppIndicator3.Indicator.new(
            "openvpn-gui",
            ICON_DISCONNECTED,
            _AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self._ind.set_status(_AppIndicator3.IndicatorStatus.ACTIVE)
        self._menu = self._build_menu()
        self._ind.set_menu(self._menu)

    def _setup_status_icon(self):
        self._si = Gtk.StatusIcon()
        self._si.set_from_file(ICON_DISCONNECTED)
        self._si.set_tooltip_text("OpenVPN GUI — Disconnected")
        self._si.set_visible(True)
        self._si.connect("activate", lambda _: self._on_show())
        self._si.connect("popup-menu", self._si_popup)

    # ── Menu ───────────────────────────────────────────────────────────────── #

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        # App title (non-interactive)
        title = Gtk.MenuItem(label="OpenVPN GUI")
        title.set_sensitive(False)
        menu.append(title)
        menu.append(Gtk.SeparatorMenuItem())

        # Dynamic connect / disconnect item
        self._menu_toggle = Gtk.MenuItem(label="Connect")
        self._menu_toggle.connect("activate", self._on_toggle)
        menu.append(self._menu_toggle)

        # Open window
        open_item = Gtk.MenuItem(label="Open")
        open_item.connect("activate", lambda _: self._on_show())
        menu.append(open_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self._on_quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _si_popup(self, icon, button, time):
        menu = self._build_menu()
        menu.popup(
            None, None,
            Gtk.StatusIcon.position_menu,
            icon, button, time,
        )

    def _on_toggle(self, *_):
        if self._connect_toggle_cb:
            self._connect_toggle_cb()

    # ── Public API ─────────────────────────────────────────────────────────── #

    def set_connect_toggle_callback(self, cb: callable):
        self._connect_toggle_cb = cb

    def set_connected(self, connected: bool, profile_name: str = ""):
        self._connected = connected
        self._active_profile = profile_name

        icon = ICON_CONNECTED if connected else ICON_DISCONNECTED
        label = "Disconnect" if connected else "Connect"
        tip = (
            f"OpenVPN GUI — Connected to {profile_name}"
            if connected
            else "OpenVPN GUI — Disconnected"
        )

        if self._use_indicator:
            self._ind.set_icon_full(
                icon,
                "VPN Connected" if connected else "VPN Disconnected",
            )
            if hasattr(self, "_menu_toggle"):
                self._menu_toggle.set_label(label)
        else:
            self._si.set_from_file(icon)
            self._si.set_tooltip_text(tip)
