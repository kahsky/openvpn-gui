"""
Main application window.

Layout:
  ┌─ HeaderBar (Dukiwi navy) ────────────────────────────────────────────┐
  │  OpenVPN GUI · by Dukiwi                      [ⓘ] [+ manual] [📂]    │
  ├─ Paned ──────────────────────────────────────────────────────────────┤
  │ Sidebar (navy)        │  Detail panel                                │
  │  • Profile list       │   Shield + name / host:port / status   [🗑]  │
  │    (name + host:port) │   ───────────────────────────────            │
  │                       │   body = Stack                               │
  │  [+ Import .ovpn]     │     form       : HOST / PORT / PROTOCOL      │
  │  [✎ Manual profile]   │                  USERNAME / PASSWORD         │
  │                       │     connecting : animation + steps + more ▾  │
  │  DUKIWI  v1.1.0       │     connected  : live traffic dashboard      │
  │                       │   [verbose log revealer]                     │
  │                       │   [ CONNECT / CANCEL / DISCONNECT ]          │
  └───────────────────────┴──────────────────────────────────────────────┘
"""
import hashlib
import os
import queue
import re
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

from . import __version__
from . import credentials as cred_store
from . import config
from . import theme
from .i18n import _
from .vpn_manager import VPNManager, DEFAULT_PORT, parse_remote
from .monitor import JournalTail, VpnStatePoller, TrafficSampler
from .widgets import (
    ConnectAnimation, StepIndicator, TrafficGraph, LogView, LogoWidget,
    format_bytes, format_duration,
)
from .dialogs import ManualProfileDialog, show_about

_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)

# Journal patterns that advance the step indicator while connecting
_STEP_PATTERNS = [
    (1, re.compile(r"ConnectInteractive|need authentication|Need 'Auth'|TLS: Initial packet|"
                   r"VERIFY|TLS handshake|Attempting to establish TCP|link remote", re.I)),
    (2, re.compile(r"Peer Connection Initiated|TUN/TAP device|Control Channel|Data Channel", re.I)),
    (3, re.compile(r"PUSH: Received|IP Config Get|Initialization Sequence Completed|Data: |"
                   r"new Tun device|Tunnel Device|ip-config", re.I)),
]
# NetworkManager VPN state → step floor
_NM_STATE_STEP = {1: 0, 2: 1, 3: 1, 4: 3}
_AUTH_FAILED_RE = re.compile(r"AUTH_FAILED|auth-failure", re.I)


# ── Helper: load SVG as pixbuf at a given size ─────────────────────────────── #

def _svg_pixbuf(name: str, size: int, scale: int = 1):
    path = os.path.join(_ASSETS, name)
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size * scale, size * scale)
    except Exception:
        return None


def _set_image_svg(image: Gtk.Image, name: str, size: int):
    """Set a crisp (HiDPI-aware) SVG into a Gtk.Image."""
    scale = image.get_scale_factor()
    pb = _svg_pixbuf(name, size, scale)
    if pb is None:
        return
    surface = Gdk.cairo_surface_create_from_pixbuf(pb, scale, image.get_window())
    image.set_from_surface(surface)


def _chip(text: str = "") -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.get_style_context().add_class("info-chip")
    lbl.set_ellipsize(Pango.EllipsizeMode.END)
    return lbl


# ── Profile list row ──────────────────────────────────────────────────────── #

class ProfileRow(Gtk.ListBoxRow):
    def __init__(self, profile: dict):
        super().__init__()
        self.profile = profile
        self._connecting = False
        self.get_style_context().add_class("profile-row")

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.dot = Gtk.Box()
        self.dot.set_size_request(9, 9)
        self.dot.set_valign(Gtk.Align.START)
        self.dot.get_style_context().add_class("dot")
        self._update_dot()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.name_label = Gtk.Label(label=profile["name"], xalign=0)
        self.name_label.get_style_context().add_class("profile-row-name")
        self.name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.server_label = Gtk.Label(label="", xalign=0)
        self.server_label.get_style_context().add_class("profile-row-server")
        self.server_label.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.pack_start(self.name_label, False, False, 0)
        vbox.pack_start(self.server_label, False, False, 0)

        hbox.pack_start(self.dot, False, False, 0)
        hbox.pack_start(vbox, True, True, 0)
        self.add(hbox)
        self.show_all()

    def _update_dot(self):
        sc = self.dot.get_style_context()
        for cls in ("dot-connected", "dot-disconnected", "dot-connecting"):
            sc.remove_class(cls)
        if self._connecting:
            sc.add_class("dot-connecting")
        elif self.profile.get("connected"):
            sc.add_class("dot-connected")
        else:
            sc.add_class("dot-disconnected")

    def update_profile(self, profile: dict):
        self.profile = profile
        self.name_label.set_text(profile["name"])
        self._update_dot()

    def set_connecting(self, connecting: bool):
        self._connecting = connecting
        self._update_dot()

    def set_server(self, server: str):
        self.server_label.set_text(server)


# ── Main window ───────────────────────────────────────────────────────────── #

class MainWindow(Gtk.ApplicationWindow):

    _STATE_IDLE = "idle"
    _STATE_CONNECTING = "connecting"
    _STATE_FINISHING = "finishing"        # short success / failure animation
    _STATE_DISCONNECTING = "disconnecting"

    def __init__(self, application, vpn_manager: VPNManager, tray):
        super().__init__(application=application, title="OpenVPN GUI")
        self._vpn = vpn_manager
        self._tray = tray
        self._selected_profile = None
        self._busy_profile = None
        self._state = self._STATE_IDLE
        self._poll_id = None
        self._loading = False            # suppress "changed" handlers while filling the form
        self._settings_dirty = False
        self._username_dirty = False
        self._cancel_requested = False
        self._abort_reason = ""          # set when the app itself aborts a connect (e.g. AUTH_FAILED)
        self._last_err_hint = ""
        self._session_start = 0.0
        self._duration_id = None
        self._journal = JournalTail(self._on_journal_line, self._on_journal_notice)
        self._poller = None
        self._sampler = None
        self._syncing_toggles = False
        self._last_creds = {}        # profile → hash of credentials used for the last successful connect
        self._creds_token = 0        # guards asynchronous keyring loads
        # Single worker for NetworkManager writes (profile edits, connect): keeps the GTK thread
        # responsive (polkit-gated nmcli calls take ~2 s) while preserving their order.
        self._nm_queue = queue.Queue()
        threading.Thread(target=self._nm_worker, daemon=True).start()

        self._vpn.set_logger(self._log_from_thread)

        theme.apply_css()
        self._build_ui()
        self._set_app_icon()

        self.set_default_size(900, 680)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._on_delete)
        self.connect("destroy", self._on_destroy)

        self._refresh_profiles()
        self._poll_id = GLib.timeout_add_seconds(4, self._poll_state)

    # ── App icon ─────────────────────────────────────────────────────────── #

    def _set_app_icon(self):
        pb = _svg_pixbuf("icon_app.svg", 64)
        if pb:
            self.set_icon(pb)

    # ── Background NetworkManager worker ─────────────────────────────────── #

    def _nm_worker(self):
        while True:
            job = self._nm_queue.get()
            try:
                job()
            except Exception as exc:
                self._log_from_thread("err", f"background task failed: {exc}")

    def _enqueue(self, fn, *args):
        self._nm_queue.put(lambda: fn(*args))

    # ── Logging helpers ──────────────────────────────────────────────────── #

    def _log_from_thread(self, level: str, msg: str):
        GLib.idle_add(self._log.append, "app", msg, level)

    def _log_app(self, msg: str, level: str = "info"):
        self._log.append("app", msg, level)

    # ── UI Construction ───────────────────────────────────────────────────── #

    def _build_ui(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("OpenVPN GUI")
        header.set_subtitle(_("by Dukiwi"))
        header.get_style_context().add_class("dk-header")
        self.set_titlebar(header)

        import_btn = Gtk.Button()
        import_btn.set_tooltip_text(_("Import .ovpn config file"))
        import_btn.set_image(Gtk.Image.new_from_icon_name("document-open-symbolic", Gtk.IconSize.BUTTON))
        import_btn.connect("clicked", self._on_import_clicked)
        header.pack_end(import_btn)

        manual_btn = Gtk.Button()
        manual_btn.set_tooltip_text(_("New manual profile (host, port, user, password)"))
        manual_btn.set_image(Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON))
        manual_btn.connect("clicked", self._on_manual_clicked)
        header.pack_end(manual_btn)

        about_btn = Gtk.Button()
        about_btn.set_tooltip_text(_("About OpenVPN GUI"))
        about_btn.set_image(Gtk.Image.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON))
        about_btn.connect("clicked", lambda *_a: show_about(self))
        header.pack_start(about_btn)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(250)
        self.add(paned)
        paned.pack1(self._build_sidebar(), resize=False, shrink=False)
        paned.pack2(self._build_detail_panel(), resize=True, shrink=False)

    # ── Sidebar ───────────────────────────────────────────────────────────── #

    def _build_sidebar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.get_style_context().add_class("sidebar")
        box.set_size_request(230, -1)

        header = Gtk.Label(label=_("VPN PROFILES"), xalign=0)
        header.get_style_context().add_class("sidebar-header")
        box.pack_start(header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._profile_list = Gtk.ListBox()
        self._profile_list.get_style_context().add_class("profile-list")
        self._profile_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._profile_list.connect("row-selected", self._on_profile_selected)
        self._profile_list.set_activate_on_single_click(True)

        self._list_empty_label = Gtk.Label(label=_("No profiles yet.\nImport a .ovpn file\nor create one manually."))
        self._list_empty_label.set_justify(Gtk.Justification.CENTER)
        self._list_empty_label.get_style_context().add_class("empty-list-label")
        self._list_empty_label.set_margin_top(30)
        self._profile_list.set_placeholder(self._list_empty_label)
        scroll.add(self._profile_list)
        box.pack_start(scroll, True, True, 0)

        import_btn = Gtk.Button(label=_("+ Import .ovpn"))
        import_btn.get_style_context().add_class("sidebar-btn")
        import_btn.connect("clicked", self._on_import_clicked)
        box.pack_start(import_btn, False, False, 0)

        manual_btn = Gtk.Button(label=_("✎ Manual profile"))
        manual_btn.get_style_context().add_class("sidebar-btn")
        manual_btn.connect("clicked", self._on_manual_clicked)
        box.pack_start(manual_btn, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.get_style_context().add_class("sidebar-footer")
        logo = LogoWidget(height=16, color=(1, 1, 1, 0.8))
        logo.set_halign(Gtk.Align.START)
        footer.pack_start(logo, False, False, 0)
        ver = Gtk.Label(label=f"v{__version__}", xalign=1)
        footer.pack_end(ver, False, False, 0)
        box.pack_start(footer, False, False, 0)
        return box

    # ── Detail panel ─────────────────────────────────────────────────────── #

    def _build_detail_panel(self) -> Gtk.Widget:
        self._detail_stack = Gtk.Stack()
        self._detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._detail_stack.set_transition_duration(150)

        # ── Empty page ─────────────────────── #
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_img = Gtk.Image()
        empty_img.set_opacity(0.35)
        empty_img.connect("realize", lambda im: _set_image_svg(im, "icon_app.svg", 80))
        empty_lbl = Gtk.Label(label=_("Select a profile, import a .ovpn file\nor define a server manually."))
        empty_lbl.get_style_context().add_class("empty-panel-label")
        empty_lbl.set_justify(Gtk.Justification.CENTER)
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_row.set_halign(Gtk.Align.CENTER)
        b1 = Gtk.Button(label=_("Import .ovpn"))
        b1.connect("clicked", self._on_import_clicked)
        b2 = Gtk.Button(label=_("Create manually"))
        b2.connect("clicked", self._on_manual_clicked)
        btn_row.pack_start(b1, False, False, 0)
        btn_row.pack_start(b2, False, False, 0)
        empty_box.pack_start(empty_img, False, False, 0)
        empty_box.pack_start(empty_lbl, False, False, 0)
        empty_box.pack_start(btn_row, False, False, 6)
        self._detail_stack.add_named(empty_box, "empty")

        # ── Profile page ───────────────────── #
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("detail-panel")

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        status_row.set_margin_bottom(6)
        self._status_image = Gtk.Image()
        self._status_image.set_size_request(52, 52)
        status_row.pack_start(self._status_image, False, False, 0)

        status_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        status_vbox.set_valign(Gtk.Align.CENTER)
        self._profile_title = Gtk.Label(label="", xalign=0)
        self._profile_title.get_style_context().add_class("profile-title")
        self._profile_title.set_ellipsize(Pango.EllipsizeMode.END)
        self._server_label = Gtk.Label(label="", xalign=0)
        self._server_label.get_style_context().add_class("profile-server-label")
        self._server_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._status_label = Gtk.Label(label=_("Disconnected"), xalign=0)
        self._status_label.get_style_context().add_class("status-label")
        self._status_label.get_style_context().add_class("status-disconnected")
        status_vbox.pack_start(self._profile_title, False, False, 0)
        status_vbox.pack_start(self._server_label, False, False, 0)
        status_vbox.pack_start(self._status_label, False, False, 0)
        status_row.pack_start(status_vbox, True, True, 0)

        delete_btn = Gtk.Button()
        delete_btn.set_tooltip_text(_("Remove this profile"))
        delete_btn.set_image(Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON))
        delete_btn.set_valign(Gtk.Align.START)
        delete_btn.get_style_context().add_class("destructive-action")
        delete_btn.connect("clicked", self._on_delete_profile)
        status_row.pack_end(delete_btn, False, False, 0)
        outer.pack_start(status_row, False, False, 0)

        sep = Gtk.Separator()
        sep.get_style_context().add_class("section-sep")
        outer.pack_start(sep, False, False, 0)

        # Body stack: form / connecting / connected
        self._body = Gtk.Stack()
        self._body.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._body.set_transition_duration(280)
        self._body.set_vhomogeneous(False)
        self._body.add_named(self._build_form_page(), "form")
        self._body.add_named(self._build_connecting_page(), "connecting")
        self._body.add_named(self._build_connected_page(), "connected")
        outer.pack_start(self._body, False, False, 0)

        # Verbose log (revealer)
        self._log = LogView(min_height=160)
        self._log_revealer = Gtk.Revealer()
        self._log_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._log_revealer.set_transition_duration(250)
        self._log_revealer.set_margin_top(12)
        self._log_revealer.add(self._log)
        self._log_revealer.set_reveal_child(False)
        outer.pack_start(self._log_revealer, True, True, 0)

        # Primary action button
        self._connect_btn = Gtk.Button(label=_("CONNECT"))
        self._connect_btn.get_style_context().add_class("connect-btn")
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        outer.pack_end(self._connect_btn, False, False, 0)

        self._detail_stack.add_named(outer, "profile")
        self._detail_stack.set_visible_child_name("empty")
        return self._detail_stack

    # -- form page ---------------------------------------------------------- #

    def _build_form_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Error bar (hidden by default)
        self._error_bar = Gtk.InfoBar()
        self._error_bar.set_message_type(Gtk.MessageType.ERROR)
        self._error_bar.set_show_close_button(True)
        self._error_bar.add_button(_("Details"), 1)
        self._error_bar.connect("response", self._on_error_bar_response)
        self._error_label = Gtk.Label(label="", xalign=0)
        self._error_label.set_line_wrap(True)
        self._error_label.set_selectable(True)
        self._error_bar.get_content_area().add(self._error_label)
        self._error_bar.set_no_show_all(True)
        self._error_bar.set_margin_bottom(8)
        page.pack_start(self._error_bar, False, False, 0)

        # SERVER section
        sec1 = Gtk.Label(label=_("SERVER"), xalign=0)
        sec1.get_style_context().add_class("section-title")
        page.pack_start(sec1, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(4)
        grid.set_margin_bottom(4)
        host_lbl = Gtk.Label(label=_("HOST"), xalign=0); host_lbl.get_style_context().add_class("field-label")
        port_lbl = Gtk.Label(label=_("PORT"), xalign=0); port_lbl.get_style_context().add_class("field-label")
        proto_lbl = Gtk.Label(label=_("PROTOCOL"), xalign=0); proto_lbl.get_style_context().add_class("field-label")

        self._host_entry = Gtk.Entry()
        self._host_entry.set_placeholder_text("vpn.example.com")
        self._host_entry.get_style_context().add_class("field-entry")
        self._host_entry.set_hexpand(True)
        self._host_entry.connect("changed", self._on_server_changed)
        self._host_entry.connect("focus-out-event", self._on_server_focus_out)
        self._host_entry.connect("activate", lambda *_a: self._save_settings_if_dirty())

        self._port_spin = Gtk.SpinButton.new_with_range(1, 65535, 1)
        self._port_spin.set_value(DEFAULT_PORT)
        self._port_spin.set_tooltip_text(_("OpenVPN default: 1194"))
        self._port_spin.get_style_context().add_class("field-entry")
        self._port_spin.set_width_chars(6)
        self._port_spin.connect("value-changed", self._on_server_changed)
        self._port_spin.connect("focus-out-event", self._on_server_focus_out)

        self._proto_combo = Gtk.ComboBoxText()
        self._proto_combo.append("udp", "UDP")
        self._proto_combo.append("tcp", "TCP")
        self._proto_combo.set_active_id("udp")
        self._proto_combo.connect("changed", self._on_proto_changed)

        grid.attach(host_lbl, 0, 0, 1, 1)
        grid.attach(port_lbl, 1, 0, 1, 1)
        grid.attach(proto_lbl, 2, 0, 1, 1)
        grid.attach(self._host_entry, 0, 1, 1, 1)
        grid.attach(self._port_spin, 1, 1, 1, 1)
        grid.attach(self._proto_combo, 2, 1, 1, 1)
        page.pack_start(grid, False, False, 0)

        self._server_hint = Gtk.Label(
            label=_("Saved to the NetworkManager profile when you leave a field or connect."),
            xalign=0,
        )
        self._server_hint.get_style_context().add_class("hint-label")
        page.pack_start(self._server_hint, False, False, 0)

        sep = Gtk.Separator()
        sep.get_style_context().add_class("section-sep")
        page.pack_start(sep, False, False, 0)

        # CREDENTIALS section
        sec2 = Gtk.Label(label=_("CREDENTIALS"), xalign=0)
        sec2.get_style_context().add_class("section-title")
        page.pack_start(sec2, False, False, 0)

        cred_grid = Gtk.Grid()
        cred_grid.set_column_spacing(12)
        cred_grid.set_row_spacing(4)
        user_lbl = Gtk.Label(label=_("USERNAME"), xalign=0); user_lbl.get_style_context().add_class("field-label")
        pass_lbl = Gtk.Label(label=_("PASSWORD"), xalign=0); pass_lbl.get_style_context().add_class("field-label")

        self._username_entry = Gtk.Entry()
        self._username_entry.set_placeholder_text(_("Enter username…"))
        self._username_entry.get_style_context().add_class("field-entry")
        self._username_entry.set_hexpand(True)
        self._username_entry.connect("changed", self._on_username_changed)
        self._username_entry.connect("focus-out-event", self._on_username_focus_out)

        pass_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._password_entry = Gtk.Entry()
        self._password_entry.set_placeholder_text(_("Enter password…"))
        self._password_entry.set_visibility(False)
        self._password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self._password_entry.get_style_context().add_class("field-entry")
        self._password_entry.set_hexpand(True)
        self._password_entry.connect("activate", lambda *_a: self._on_connect_clicked(None))
        self._eye_btn = Gtk.ToggleButton()
        self._eye_btn.set_image(Gtk.Image.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.BUTTON))
        self._eye_btn.set_tooltip_text(_("Show / hide password"))
        self._eye_btn.connect("toggled", lambda b: self._password_entry.set_visibility(b.get_active()))
        self._eye_btn.get_style_context().add_class("flat")
        pass_box.pack_start(self._password_entry, True, True, 0)
        pass_box.pack_start(self._eye_btn, False, False, 0)

        cred_grid.attach(user_lbl, 0, 0, 1, 1)
        cred_grid.attach(self._username_entry, 0, 1, 1, 1)
        cred_grid.attach(pass_lbl, 1, 0, 1, 1)
        cred_grid.attach(pass_box, 1, 1, 1, 1)
        page.pack_start(cred_grid, False, False, 0)

        self._remember_check = Gtk.CheckButton(label=_("Remember credentials (stored in system keyring)"))
        self._remember_check.set_margin_top(6)
        self._remember_check.connect("toggled", self._on_remember_toggled)
        page.pack_start(self._remember_check, False, False, 0)
        return page

    # -- connecting page ---------------------------------------------------- #

    def _build_connecting_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.set_valign(Gtk.Align.CENTER)

        self._anim = ConnectAnimation(size=180)
        page.pack_start(self._anim, False, False, 0)

        self._connecting_title = Gtk.Label(label="")
        self._connecting_title.get_style_context().add_class("connecting-title")
        self._connecting_title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        page.pack_start(self._connecting_title, False, False, 0)

        self._connecting_detail = Gtk.Label(label="")
        self._connecting_detail.get_style_context().add_class("connecting-detail")
        self._connecting_detail.set_ellipsize(Pango.EllipsizeMode.END)
        self._connecting_detail.set_max_width_chars(70)
        page.pack_start(self._connecting_detail, False, False, 0)

        self._steps = StepIndicator([
            _("Preparing"), _("Authenticating"), _("Establishing tunnel"), _("Configuring network"),
        ])
        self._steps.set_margin_top(6)
        page.pack_start(self._steps, False, False, 0)

        self._more_btn_connecting = self._make_more_button()
        page.pack_start(self._more_btn_connecting, False, False, 4)
        return page

    # -- connected page ----------------------------------------------------- #

    def _build_connected_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._chip_duration = _chip()
        self._chip_ip = _chip()
        self._chip_iface = _chip()
        self._chip_gateway = _chip()
        for c in (self._chip_duration, self._chip_ip, self._chip_iface, self._chip_gateway):
            chips.pack_start(c, False, False, 0)
        page.pack_start(chips, False, False, 0)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("card")
        card.get_style_context().add_class("card-blue")

        stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        dl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        dl_lbl = Gtk.Label(label="↓  " + _("DOWNLOAD"), xalign=0); dl_lbl.get_style_context().add_class("stat-label")
        self._dl_value = Gtk.Label(label="0 B/s", xalign=0); self._dl_value.get_style_context().add_class("stat-value")
        dl_box.pack_start(dl_lbl, False, False, 0)
        dl_box.pack_start(self._dl_value, False, False, 0)
        ul_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        ul_lbl = Gtk.Label(label="↑  " + _("UPLOAD"), xalign=0); ul_lbl.get_style_context().add_class("stat-label")
        self._ul_value = Gtk.Label(label="0 B/s", xalign=0)
        self._ul_value.get_style_context().add_class("stat-value")
        self._ul_value.get_style_context().add_class("stat-value-up")
        ul_box.pack_start(ul_lbl, False, False, 0)
        ul_box.pack_start(self._ul_value, False, False, 0)
        stats.pack_start(dl_box, False, False, 0)
        stats.pack_start(ul_box, False, False, 0)

        self._peak_label = Gtk.Label(label="", xalign=1)
        self._peak_label.get_style_context().add_class("stat-sub")
        self._peak_label.set_valign(Gtk.Align.END)
        stats.pack_end(self._peak_label, False, False, 0)
        card.pack_start(stats, False, False, 0)

        self._graph = TrafficGraph(samples=90, height=118)
        card.pack_start(self._graph, False, False, 0)

        totals = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        self._total_rx = Gtk.Label(label="", xalign=0); self._total_rx.get_style_context().add_class("stat-sub")
        self._total_tx = Gtk.Label(label="", xalign=0); self._total_tx.get_style_context().add_class("stat-sub")
        self._dns_label = Gtk.Label(label="", xalign=1); self._dns_label.get_style_context().add_class("stat-sub")
        self._dns_label.set_ellipsize(Pango.EllipsizeMode.END)
        totals.pack_start(self._total_rx, False, False, 0)
        totals.pack_start(self._total_tx, False, False, 0)
        totals.pack_end(self._dns_label, False, False, 0)
        card.pack_start(totals, False, False, 0)
        page.pack_start(card, False, False, 0)

        self._more_btn_connected = self._make_more_button()
        self._more_btn_connected.set_halign(Gtk.Align.START)
        page.pack_start(self._more_btn_connected, False, False, 0)
        return page

    def _make_more_button(self) -> Gtk.ToggleButton:
        btn = Gtk.ToggleButton(label=_("See more") + "  ▾")
        btn.get_style_context().add_class("more-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("toggled", self._on_more_toggled)
        return btn

    # ── Verbose log visibility ───────────────────────────────────────────── #

    def _on_more_toggled(self, btn):
        if self._syncing_toggles:
            return
        self._set_log_visible(btn.get_active())

    def _set_log_visible(self, visible: bool):
        self._syncing_toggles = True
        self._log_revealer.set_reveal_child(visible)
        label = (_("See less") + "  ▴") if visible else (_("See more") + "  ▾")
        for b in (self._more_btn_connecting, self._more_btn_connected):
            b.set_active(visible)
            b.set_label(label)
        self._syncing_toggles = False

    def _on_error_bar_response(self, bar, response):
        if response == 1:
            self._set_log_visible(True)
        else:
            bar.hide()

    def _show_error_bar(self, text: str):
        self._error_label.set_text(text)
        self._error_bar.show()
        self._error_label.show()

    # ── Profile management ────────────────────────────────────────────────── #

    def _refresh_profiles(self):
        """Reload all VPN profiles from NetworkManager and rebuild the list."""
        profiles = self._vpn.get_profiles()
        for row in self._profile_list.get_children():
            self._profile_list.remove(row)
        for profile in profiles:
            row = ProfileRow(profile)
            self._profile_list.add(row)
            threading.Thread(
                target=self._load_server_for_row, args=(row, profile["name"]), daemon=True
            ).start()
        self._profile_list.show_all()

        last = config.get("last_selected_profile")
        if last:
            for row in self._profile_list.get_children():
                if isinstance(row, ProfileRow) and row.profile["name"] == last:
                    self._profile_list.select_row(row)
                    break

    def _load_server_for_row(self, row: ProfileRow, profile_name: str):
        server = self._vpn.get_server(profile_name)
        GLib.idle_add(row.set_server, server)

    def _profile_names(self):
        return [r.profile["name"] for r in self._profile_list.get_children() if isinstance(r, ProfileRow)]

    def _select_profile_by_name(self, name: str):
        for row in self._profile_list.get_children():
            if isinstance(row, ProfileRow) and row.profile["name"] == name:
                self._profile_list.select_row(row)
                return True
        return False

    def _row_for(self, name: str):
        for row in self._profile_list.get_children():
            if isinstance(row, ProfileRow) and row.profile["name"] == name:
                return row
        return None

    def _on_profile_selected(self, listbox, row):
        if not isinstance(row, ProfileRow):
            self._selected_profile = None
            self._stop_sampler()
            self._detail_stack.set_visible_child_name("empty")
            return

        profile = row.profile
        self._selected_profile = profile["name"]
        config.set_value("last_selected_profile", profile["name"])
        self._profile_title.set_text(profile["name"])
        self._error_bar.hide()

        # Server settings from NetworkManager
        details = self._vpn.get_profile_details(profile["name"])
        self._loading = True
        self._host_entry.set_text(details["host"])
        self._port_spin.set_value(details["port"] or DEFAULT_PORT)
        self._proto_combo.set_active_id(details["proto"] or "udp")
        self._username_entry.set_text(details["username"])
        self._password_entry.set_text("")
        self._remember_check.set_active(False)
        self._loading = False
        self._settings_dirty = False
        self._username_dirty = False
        self._update_server_label()
        if len(details["remotes"]) > 1:
            self._server_hint.set_text(
                _("This profile lists {n} servers; editing here keeps only the first one.")
                .format(n=len(details["remotes"]))
            )
        else:
            self._server_hint.set_text(
                _("Saved to the NetworkManager profile when you leave a field or connect."))

        # Credentials from keyring (asynchronous: Secret Service can take a second or two)
        self._creds_token += 1
        if config.has_saved_creds(profile["name"]):
            self._loading = True
            self._remember_check.set_active(True)
            self._loading = False
            threading.Thread(
                target=self._bg_load_creds, args=(profile["name"], self._creds_token), daemon=True
            ).start()

        if self._vpn.is_connected(profile["name"]):
            self._enter_connected_view()
        else:
            self._enter_form_view()
        self._detail_stack.set_visible_child_name("profile")

    def _bg_load_creds(self, name: str, token: int):
        try:
            username, password = cred_store.load(name)
        except Exception as exc:
            self._log_from_thread("warn", _("Keyring error: {msg}").format(msg=exc))
            return
        GLib.idle_add(self._apply_loaded_creds, name, token, username, password)

    def _apply_loaded_creds(self, name: str, token: int, username: str, password: str) -> bool:
        if token != self._creds_token or self._selected_profile != name:
            return False
        self._loading = True
        if username:
            self._username_entry.set_text(username)
        if password and not self._password_entry.get_text():
            self._password_entry.set_text(password)
        self._loading = False
        return False

    def _update_server_label(self):
        host = self._host_entry.get_text().strip()
        port = self._port_spin.get_value_as_int()
        proto = (self._proto_combo.get_active_id() or "udp").upper()
        self._server_label.set_text(f"{host}:{port}  ·  {proto}" if host else _("No server defined"))

    # ── Form field persistence ────────────────────────────────────────────── #

    def _on_server_changed(self, *_a):
        if self._loading:
            return
        self._settings_dirty = True
        self._update_server_label()

    def _on_proto_changed(self, *_a):
        if self._loading:
            return
        self._settings_dirty = True
        self._update_server_label()
        self._save_settings_if_dirty()

    def _on_server_focus_out(self, *_a):
        self._save_settings_if_dirty()
        return False

    def _on_username_changed(self, *_a):
        if not self._loading:
            self._username_dirty = True

    def _on_username_focus_out(self, *_a):
        self._save_username_if_dirty()
        return False

    def _save_settings_if_dirty(self) -> bool:
        """Persist host/port/proto to NM. Returns False on validation error."""
        if not self._settings_dirty or not self._selected_profile:
            return True
        host = self._host_entry.get_text().strip()
        port = self._port_spin.get_value_as_int()
        proto = self._proto_combo.get_active_id() or "udp"
        if not host:
            return False
        self._settings_dirty = False
        profile = self._selected_profile
        self._log_app(_("Saving server settings: {host}:{port} ({proto})").format(
            host=host, port=port, proto=proto.upper()))
        row = self._row_for(profile)
        if row:
            row.set_server(f"{host}:{port}")
        self._enqueue(self._bg_save_settings, profile, host, port, proto)
        return True

    def _bg_save_settings(self, profile: str, host: str, port: int, proto: str):
        ok, msg = self._vpn.set_remote(profile, host, port, proto)
        if not ok:
            GLib.idle_add(self._on_save_settings_failed, profile, msg)

    def _on_save_settings_failed(self, profile: str, msg: str) -> bool:
        if self._selected_profile == profile:
            self._settings_dirty = True
            self._show_error_bar(_("Could not save server settings: {msg}").format(msg=msg))
        return False

    def _save_username_if_dirty(self):
        if not self._username_dirty or not self._selected_profile:
            return
        self._username_dirty = False
        username = self._username_entry.get_text().strip()
        self._enqueue(self._vpn.set_username, self._selected_profile, username)

    # ── View states ──────────────────────────────────────────────────────── #

    def _set_status(self, text: str, cls: str, icon: str):
        sc = self._status_label.get_style_context()
        for c in ("status-connected", "status-disconnected", "status-busy", "status-error"):
            sc.remove_class(c)
        sc.add_class(cls)
        self._status_label.set_text(text)
        _set_image_svg(self._status_image, icon, 52)

    def _set_button(self, label: str, secondary: bool, sensitive: bool = True):
        sc = self._connect_btn.get_style_context()
        if secondary:
            sc.add_class("secondary")
        else:
            sc.remove_class("secondary")
        self._connect_btn.set_label(label)
        self._connect_btn.set_sensitive(sensitive)

    def _enter_form_view(self):
        self._stop_sampler()
        self._stop_duration_timer()
        self._anim.stop()
        self._steps.stop()
        self._body.set_visible_child_name("form")
        self._set_status(_("Disconnected"), "status-disconnected", "icon_disconnected.svg")
        self._set_button(_("CONNECT"), secondary=False)
        self._set_form_sensitive(True)

    def _enter_connecting_view(self, host: str, port: int):
        self._anim.start("connecting")
        self._steps.reset()
        self._steps.start()
        self._connecting_title.set_text(_("Connecting to {server}…").format(server=f"{host}:{port}"))
        self._connecting_detail.set_text(_("Asking NetworkManager to bring the tunnel up…"))
        self._body.set_visible_child_name("connecting")
        self._set_status(_("Connecting…"), "status-busy", "icon_connecting.svg")
        self._set_button(_("CANCEL"), secondary=True)

    def _enter_connected_view(self):
        name = self._selected_profile
        info = self._vpn.get_active_info(name)
        ts = self._vpn.get_activation_timestamp(name)
        self._session_start = float(ts) if ts else time.time()
        self._anim.stop()
        self._steps.stop()

        ip4 = info["ip4"] or "—"
        self._chip_ip.set_text(_("IP {ip}").format(ip=ip4))
        self._chip_iface.set_text(info["iface"] or "tun?")
        gw = info["gateway"] or self._server_label.get_text()
        if info["gateway"]:
            g_host, g_port, _g_proto = parse_remote(info["gateway"])
            gw = f"{g_host}:{g_port}" if g_port else g_host
        self._chip_gateway.set_text(_("via {server}").format(server=gw))
        self._dns_label.set_text(("DNS " + ", ".join(info["dns"])) if info["dns"] else "")
        self._peak_label.set_text("")
        self._update_duration_chip()
        self._start_duration_timer()

        self._graph.reset()
        self._dl_value.set_text(format_bytes(0, True))
        self._ul_value.set_text(format_bytes(0, True))
        rx, tx = self._vpn.read_iface_counters(info["iface"]) if info["iface"] else (0, 0)
        self._total_rx.set_text(_("Received {v}").format(v=format_bytes(rx)))
        self._total_tx.set_text(_("Sent {v}").format(v=format_bytes(tx)))
        self._start_sampler(info["iface"])

        self._body.set_visible_child_name("connected")
        self._set_status(_("Connected"), "status-connected", "icon_connected.svg")
        self._set_button(_("DISCONNECT"), secondary=True)
        self._error_bar.hide()
        if info["iface"]:
            self._log_app(_("Tunnel up on {iface} — IP {ip}, gateway {gw}").format(
                iface=info["iface"], ip=ip4, gw=gw), "ok")

    def _set_form_sensitive(self, sensitive: bool):
        for w in (self._host_entry, self._port_spin, self._proto_combo,
                  self._username_entry, self._password_entry, self._remember_check):
            w.set_sensitive(sensitive)

    # -- traffic sampling --------------------------------------------------- #

    def _start_sampler(self, iface: str):
        self._stop_sampler()
        if not iface:
            self._log_app(_("Could not determine the tunnel interface — traffic view unavailable."), "warn")
            return
        self._sampler = TrafficSampler(iface, self._on_traffic_sample)
        self._sampler.start()

    def _stop_sampler(self):
        if self._sampler:
            self._sampler.stop()
            self._sampler = None

    def _on_traffic_sample(self, rx_rate, tx_rate, rx_total, tx_total):
        self._graph.push(rx_rate, tx_rate)
        self._dl_value.set_text(format_bytes(rx_rate, True))
        self._ul_value.set_text(format_bytes(tx_rate, True))
        self._total_rx.set_text(_("Received {v}").format(v=format_bytes(rx_total)))
        self._total_tx.set_text(_("Sent {v}").format(v=format_bytes(tx_total)))
        if self._sampler:
            self._peak_label.set_text(_("Peak ↓ {dl}  ↑ {ul}").format(
                dl=format_bytes(self._sampler.peak_rx, True),
                ul=format_bytes(self._sampler.peak_tx, True)))

    def _start_duration_timer(self):
        self._stop_duration_timer()
        self._duration_id = GLib.timeout_add_seconds(1, self._update_duration_chip)

    def _stop_duration_timer(self):
        if self._duration_id:
            GLib.source_remove(self._duration_id)
            self._duration_id = None

    def _update_duration_chip(self) -> bool:
        self._chip_duration.set_text(
            "●  " + _("Connected {d}").format(d=format_duration(time.time() - self._session_start)))
        return True

    # ── Import / manual creation ─────────────────────────────────────────── #

    def _on_import_clicked(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title=_("Import OpenVPN Config"), parent=self, action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(_("_Cancel"), Gtk.ResponseType.CANCEL, _("_Import"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        ovpn_filter = Gtk.FileFilter()
        ovpn_filter.set_name(_("OpenVPN Config (*.ovpn, *.conf)"))
        ovpn_filter.add_pattern("*.ovpn")
        ovpn_filter.add_pattern("*.conf")
        dialog.add_filter(ovpn_filter)
        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            dialog.destroy()
            self._do_import(filepath)
        else:
            dialog.destroy()

    def _do_import(self, filepath: str):
        ok, result = self._vpn.import_config(filepath)
        if ok:
            self._refresh_profiles()
            self._select_profile_by_name(result)
            self._show_info(_("Profile imported"), _('"{name}" has been added.').format(name=result))
        else:
            self._show_error(_("Import failed"), result)

    def _on_manual_clicked(self, _btn):
        dlg = ManualProfileDialog(self, existing_names=self._profile_names())
        while True:
            if dlg.run() != Gtk.ResponseType.OK:
                dlg.destroy()
                return
            v = dlg.get_values()
            ok, result = self._vpn.create_manual_profile(
                v["name"], v["host"], v["port"], v["proto"], v["ca"], v["username"]
            )
            if ok:
                break
            dlg.show_error(result)
        dlg.destroy()

        if v["remember"] and (v["username"] or v["password"]):
            config.mark_creds_saved(v["name"])
            threading.Thread(target=cred_store.save, args=(v["name"], v["username"], v["password"]),
                             daemon=True).start()
        self._refresh_profiles()
        self._select_profile_by_name(v["name"])
        if v["password"] and not v["remember"]:
            self._password_entry.set_text(v["password"])
        self._log_app(_("Manual profile \"{name}\" created ({host}:{port} {proto}).").format(
            name=v["name"], host=v["host"], port=v["port"], proto=v["proto"].upper()), "ok")

    # ── Delete profile ────────────────────────────────────────────────────── #

    def _on_delete_profile(self, _btn):
        if not self._selected_profile or self._state != self._STATE_IDLE:
            return
        name = self._selected_profile
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE, text=_('Delete "{name}"?').format(name=name),
        )
        dialog.format_secondary_text(
            _("This will remove the profile from NetworkManager.\nSaved credentials will also be deleted.")
        )
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        delete_btn = dialog.add_button(_("_Delete"), Gtk.ResponseType.OK)
        delete_btn.get_style_context().add_class("destructive-action")
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.destroy()
            ok, msg = self._vpn.delete_profile(name)
            if ok:
                cred_store.delete(name)
                config.unmark_creds_saved(name)
                self._selected_profile = None
                self._stop_sampler()
                self._stop_duration_timer()
                self._detail_stack.set_visible_child_name("empty")
                self._refresh_profiles()
                self._tray.set_connected(False)
            else:
                self._show_error(_("Delete failed"), msg)
        else:
            dialog.destroy()

    # ── Connect / Disconnect ─────────────────────────────────────────────── #

    def _on_connect_clicked(self, _btn):
        if not self._selected_profile:
            return
        if self._state == self._STATE_CONNECTING:
            self._cancel_connect()
            return
        if self._state != self._STATE_IDLE:
            return
        if self._vpn.is_connected(self._selected_profile):
            self._start_disconnect()
        else:
            self._start_connect()

    def _start_connect(self):
        profile = self._selected_profile
        host = self._host_entry.get_text().strip()
        port = self._port_spin.get_value_as_int()
        proto = self._proto_combo.get_active_id() or "udp"
        if not host:
            self._show_error_bar(_("Please enter the server host before connecting."))
            self._host_entry.grab_focus()
            return
        self._error_bar.hide()

        self._log_app("─" * 8 + f"  {profile}  ·  {host}:{port} {proto.upper()}  " + "─" * 8, "step")
        if not self._save_settings_if_dirty():
            return
        self._save_username_if_dirty()

        username = self._username_entry.get_text().strip()
        password = self._password_entry.get_text()
        remember = self._remember_check.get_active()
        if remember and (username or password):
            config.mark_creds_saved(profile)
        elif not remember:
            config.unmark_creds_saved(profile)

        self._state = self._STATE_CONNECTING
        self._busy_profile = profile
        self._cancel_requested = False
        self._abort_reason = ""
        self._last_err_hint = ""
        self._profile_list.set_sensitive(False)
        row = self._row_for(profile)
        if row:
            row.set_connecting(True)
        self._tray.set_connecting(profile)

        self._journal.start()
        self._poller = VpnStatePoller(self._vpn, profile, self._on_vpn_state)
        self._poller.start()
        self._enter_connecting_view(host, port)
        self._steps.set_step(0)

        creds_hash = hashlib.sha256(f"{username}\0{password}".encode()).hexdigest()
        clear_secrets = self._last_creds.get(profile) != creds_hash
        self._pending_creds_hash = creds_hash
        # Queued behind any pending profile edit so nmcli sees the new host/port first.
        self._enqueue(self._bg_connect, profile, username, password, remember, clear_secrets)

    def _bg_connect(self, profile: str, username: str, password: str, remember: bool,
                    clear_secrets: bool):
        # Keyring access can block for a while (unlock prompt, slow Secret Service):
        # keep it off the GTK main thread.
        try:
            if remember and (username or password):
                cred_store.save(profile, username, password)
                self._log_from_thread("info", _("Credentials stored in the system keyring."))
            elif not remember:
                cred_store.delete(profile)
        except Exception as exc:
            self._log_from_thread("warn", _("Keyring error: {msg}").format(msg=exc))
        if not clear_secrets:
            self._log_from_thread("info", _("Same credentials as the last successful connection — "
                                            "NetworkManager's cached secrets are kept."))
        ok, msg = self._vpn.connect(profile, username, password, clear_cached_secrets=clear_secrets)
        GLib.idle_add(self._on_connect_done, ok, msg, profile)

    def _on_connect_done(self, ok: bool, msg: str, profile: str):
        if self._poller:
            self._poller.stop()
            self._poller = None
        self._profile_list.set_sensitive(True)
        row = self._row_for(profile)
        if row:
            row.set_connecting(False)

        if ok:
            self._last_creds[profile] = getattr(self, "_pending_creds_hash", None)
            self._state = self._STATE_FINISHING
            self._set_button(_("CONNECTED"), secondary=True, sensitive=False)
            self._steps.set_done()
            self._anim.set_mode("success")
            self._connecting_detail.set_text(_("Tunnel established."))
            self._log_app(_("Connected to {name}.").format(name=profile), "ok")
            GLib.timeout_add(900, self._finish_connect_success, profile)
        elif self._cancel_requested:
            self._state = self._STATE_IDLE
            self._log_app(_("Connection cancelled by user."), "warn")
            self._journal.stop(delay=3)
            self._enter_form_view()
            self._tray.set_connected(False)
            self._refresh_sidebar_dots()
        else:
            if self._abort_reason:
                msg = self._abort_reason
            self._state = self._STATE_FINISHING
            self._set_button(_("FAILED"), secondary=True, sensitive=False)
            self._steps.set_failed()
            self._anim.set_mode("failed")
            self._connecting_detail.set_text(msg)
            self._log_app(_("Connection failed: {msg}").format(msg=msg), "err")
            self._journal.stop(delay=3)
            GLib.timeout_add(1300, self._finish_connect_failure, msg)
        return False

    def _finish_connect_success(self, profile: str) -> bool:
        self._state = self._STATE_IDLE
        if self._selected_profile == profile:
            self._enter_connected_view()
        self._tray.set_connected(True, profile)
        self._refresh_sidebar_dots()
        return False

    def _finish_connect_failure(self, msg: str) -> bool:
        self._state = self._STATE_IDLE
        self._enter_form_view()
        self._tray.set_connected(False)
        self._refresh_sidebar_dots()
        text = msg
        if self._last_err_hint and self._last_err_hint not in msg:
            text += "\n" + self._last_err_hint
        self._show_error_bar(text)
        return False

    def _cancel_connect(self):
        if self._cancel_requested or not self._busy_profile:
            return
        self._cancel_requested = True
        self._set_button(_("CANCELLING…"), secondary=True, sensitive=False)
        self._log_app(_("Cancel requested — bringing the connection down."), "warn")
        threading.Thread(
            target=self._vpn.disconnect, args=(self._busy_profile,), daemon=True
        ).start()

    def _start_disconnect(self):
        profile = self._selected_profile
        self._state = self._STATE_DISCONNECTING
        self._busy_profile = profile
        self._set_button(_("DISCONNECTING…"), secondary=True, sensitive=False)
        self._set_status(_("Disconnecting…"), "status-busy", "icon_connecting.svg")
        self._log_app("─" * 8 + "  " + _("Disconnecting {name}").format(name=profile) + "  " + "─" * 8, "step")
        self._journal.start()
        threading.Thread(target=self._bg_disconnect, args=(profile,), daemon=True).start()

    def _bg_disconnect(self, profile: str):
        ok, msg = self._vpn.disconnect(profile)
        GLib.idle_add(self._on_disconnect_done, ok, msg)

    def _on_disconnect_done(self, ok: bool, msg: str):
        self._state = self._STATE_IDLE
        self._enter_form_view()
        self._tray.set_connected(False)
        self._refresh_sidebar_dots()
        self._journal.stop(delay=3)
        if ok:
            self._log_app(_("Disconnected."), "ok")
        else:
            self._log_app(_("Disconnect failed: {msg}").format(msg=msg), "err")
            self._show_error_bar(_("Disconnect failed: {msg}").format(msg=msg))
        return False

    # Called from TrayIcon menu "Connect/Disconnect"
    def toggle_connection(self):
        if not self._selected_profile:
            return
        if self._state == self._STATE_CONNECTING:
            self._cancel_connect()
        elif self._state == self._STATE_IDLE:
            if self._vpn.is_connected(self._selected_profile):
                self._start_disconnect()
            else:
                self._start_connect()

    # ── Live feedback while connecting ───────────────────────────────────── #

    def _on_vpn_state(self, state: int, text: str) -> bool:
        if self._state == self._STATE_CONNECTING:
            self._log_app(_("NetworkManager VPN state: {s}").format(s=text or state))
            step = _NM_STATE_STEP.get(state)
            if step is not None:
                self._steps.set_step(step)
        return False

    def _on_journal_line(self, source: str, msg: str, level: str, ts: str) -> bool:
        self._log.append(source, msg, level, ts)
        if self._state == self._STATE_CONNECTING:
            for step, pat in _STEP_PATTERNS:
                if pat.search(msg):
                    self._steps.set_step(step)
            if source in ("openvpn", "NetworkMgr"):
                self._connecting_detail.set_text(msg if len(msg) < 110 else msg[:107] + "…")
            if level == "err":
                self._last_err_hint = msg
            if source == "openvpn" and _AUTH_FAILED_RE.search(msg) and not self._abort_reason \
                    and not self._cancel_requested:
                # OpenVPN would retry until NetworkManager's 60 s timeout: stop now.
                self._abort_reason = _("Authentication failed (AUTH_FAILED) — check the username and password.")
                self._log_app(self._abort_reason, "err")
                self._set_button(_("FAILED"), secondary=True, sensitive=False)
                threading.Thread(
                    target=self._vpn.disconnect, args=(self._busy_profile,), daemon=True
                ).start()
        return False

    def _on_journal_notice(self, level: str, msg: str) -> bool:
        self._log.append("app", msg, level)
        return False

    # ── Polling ───────────────────────────────────────────────────────────── #

    def _poll_state(self) -> bool:
        if self._state != self._STATE_IDLE:
            return True
        profiles = self._vpn.get_profiles()
        # Several tunnels can be up at once (one profile per network): list them all in the tray.
        connected_names = [p["name"] for p in profiles if p["connected"]]
        self._tray.set_connected(bool(connected_names), ", ".join(connected_names))

        if self._selected_profile:
            is_now = any(p["connected"] for p in profiles if p["name"] == self._selected_profile)
            showing = self._body.get_visible_child_name()
            if is_now and showing != "connected":
                self._log_app(_("Connection became active (external activation detected)."), "ok")
                self._enter_connected_view()
            elif not is_now and showing == "connected":
                self._log_app(_("Connection dropped — tunnel is no longer active."), "warn")
                self._enter_form_view()
                self._show_error_bar(_("The VPN connection was lost."))
        self._refresh_sidebar_dots(profiles)
        return True

    def _refresh_sidebar_dots(self, profiles: list = None):
        if profiles is None:
            profiles = self._vpn.get_profiles()
        name_map = {p["name"]: p for p in profiles}
        for row in self._profile_list.get_children():
            if isinstance(row, ProfileRow):
                profile = name_map.get(row.profile["name"])
                if profile:
                    row.update_profile(profile)

    # ── Credential helpers ────────────────────────────────────────────────── #

    def _on_remember_toggled(self, btn):
        if self._loading:
            return
        if not btn.get_active() and self._selected_profile:
            config.unmark_creds_saved(self._selected_profile)
            threading.Thread(target=cred_store.delete, args=(self._selected_profile,), daemon=True).start()

    # ── Window hide / show ────────────────────────────────────────────────── #

    def _on_delete(self, _widget, _event):
        if config.get("minimize_to_tray"):
            self.hide()
            return True
        return False

    def _on_destroy(self, *_a):
        self._stop_sampler()
        self._stop_duration_timer()
        if self._poller:
            self._poller.stop()
        self._journal.stop()

    def show_and_raise(self):
        self.show_all()
        self.present()
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.raise_()
            gdk_win.focus(Gdk.CURRENT_TIME)

    # ── Dialogs ───────────────────────────────────────────────────────────── #

    def _show_info(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()

    def _show_error(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()
