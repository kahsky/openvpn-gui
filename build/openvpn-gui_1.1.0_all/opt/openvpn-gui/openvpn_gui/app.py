"""
GTK Application class — ties together the window, tray and VPN manager.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from . import __app_id__
from .vpn_manager import VPNManager
from .tray import TrayIcon
from .window import MainWindow
from . import config


class OpenVPNApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id=__app_id__)
        self._vpn = VPNManager()
        self._window: MainWindow = None
        self._tray: TrayIcon = None

    # ── GTK Application lifecycle ─────────────────────────────────────────── #

    def do_startup(self):
        Gtk.Application.do_startup(self)

    def do_activate(self):
        if self._window is not None:
            # Already running — just show the window
            self._window.show_and_raise()
            return

        # Build tray first so the window can reference it
        self._tray = TrayIcon(
            on_show=self._show_window,
            on_quit=self._quit,
        )

        self._window = MainWindow(
            application=self,
            vpn_manager=self._vpn,
            tray=self._tray,
        )

        # Wire up tray toggle → window handler
        self._tray.set_connect_toggle_callback(self._window.toggle_connection)

        start_minimized = config.get("start_minimized")
        if not start_minimized:
            self._window.show_all()

    # ── Helpers ───────────────────────────────────────────────────────────── #

    def _show_window(self):
        if self._window:
            self._window.show_and_raise()

    def _quit(self):
        if self._window:
            self._window.destroy()
        self.quit()
