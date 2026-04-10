"""
Main application window.

Layout:
  ┌─ HeaderBar ──────────────────────────────────────────────────┐
  │  OpenVPN GUI                              [Import]  [⚙]      │
  ├─ Paned ──────────────────────────────────────────────────────┤
  │ Sidebar (220 px)      │  Detail panel                        │
  │  • Profile list       │   Big status shield + label          │
  │    (name + server)    │   Profile name / server              │
  │                       │   ─────────────────                  │
  │  [+ Import Config]    │   Username  ──────────               │
  │                       │   Password  ──────────  [👁]         │
  │                       │   ☐ Remember credentials             │
  │                       │   ─────────────────                  │
  │                       │   [ CONNECT / DISCONNECT ]           │
  └───────────────────────┴──────────────────────────────────────┘
"""
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

from . import credentials as cred_store
from . import config
from .vpn_manager import VPNManager

_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)

# ── CSS ────────────────────────────────────────────────────────────────────── #

_CSS = """
/* Sidebar */
.sidebar {
    background-color: mix(@theme_bg_color, @theme_base_color, 0.4);
    border-right: 1px solid @unfocused_borders;
}
.sidebar-header {
    padding: 14px 16px 10px 16px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    color: alpha(@theme_fg_color, 0.55);
}
.profile-list {
    background-color: transparent;
}
.profile-row {
    padding: 10px 14px;
}
.profile-row-name {
    font-size: 13px;
    font-weight: bold;
}
.profile-row-server {
    font-size: 11px;
    color: alpha(@theme_fg_color, 0.6);
}
.dot {
    min-width: 9px;
    min-height: 9px;
    border-radius: 5px;
    margin-right: 8px;
    margin-top: 4px;
}
.dot-connected    { background-color: #4CAF50; }
.dot-disconnected { background-color: #BDBDBD; }
.import-sidebar-btn {
    margin: 8px 10px 10px 10px;
    padding: 6px 0;
}

/* Detail panel */
.detail-panel {
    padding: 28px 32px;
}
.empty-panel-label {
    color: alpha(@theme_fg_color, 0.4);
    font-size: 14px;
}
.status-label-connected {
    font-size: 15px;
    font-weight: bold;
    color: #388E3C;
}
.status-label-disconnected {
    font-size: 15px;
    font-weight: bold;
    color: #757575;
}
.status-label-busy {
    font-size: 15px;
    font-weight: bold;
    color: #F57C00;
}
.profile-title {
    font-size: 20px;
    font-weight: bold;
}
.profile-server-label {
    font-size: 12px;
    color: alpha(@theme_fg_color, 0.6);
}
.section-sep {
    margin-top: 16px;
    margin-bottom: 16px;
}
.field-label {
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    color: alpha(@theme_fg_color, 0.6);
    margin-bottom: 3px;
}
.field-entry {
    padding: 6px 10px;
    border-radius: 5px;
}
.connect-btn {
    padding: 11px 0;
    font-size: 14px;
    font-weight: bold;
    border-radius: 6px;
    margin-top: 8px;
}
"""


def _apply_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(_CSS.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


# ── Helper: load SVG as pixbuf at a given size ─────────────────────────────── #

def _svg_pixbuf(name: str, size: int) -> GdkPixbuf.Pixbuf:
    path = os.path.join(_ASSETS, name)
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
    except Exception:
        return None


# ── Profile list row ──────────────────────────────────────────────────────── #

class ProfileRow(Gtk.ListBoxRow):
    def __init__(self, profile: dict):
        super().__init__()
        self.profile = profile
        self.get_style_context().add_class("profile-row")

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # Status dot
        self.dot = Gtk.DrawingArea()
        self.dot.set_size_request(9, 9)
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
        sc.remove_class("dot-connected")
        sc.remove_class("dot-disconnected")
        if self.profile.get("connected"):
            sc.add_class("dot-connected")
        else:
            sc.add_class("dot-disconnected")

    def update_profile(self, profile: dict):
        self.profile = profile
        self.name_label.set_text(profile["name"])
        self._update_dot()

    def set_server(self, server: str):
        self.server_label.set_text(server)


# ── Main window ───────────────────────────────────────────────────────────── #

class MainWindow(Gtk.ApplicationWindow):

    _STATE_IDLE = "idle"
    _STATE_CONNECTING = "connecting"
    _STATE_DISCONNECTING = "disconnecting"

    def __init__(self, application, vpn_manager: VPNManager, tray):
        super().__init__(application=application, title="OpenVPN GUI")
        self._vpn = vpn_manager
        self._tray = tray
        self._selected_profile = None
        self._state = self._STATE_IDLE
        self._poll_id = None

        _apply_css()
        self._build_ui()
        self._set_app_icon()

        self.set_default_size(780, 500)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Connect window-delete to hide (minimize to tray) or quit
        self.connect("delete-event", self._on_delete)

        # Initial load
        self._refresh_profiles()

        # Poll for connection state changes every 4 seconds
        self._poll_id = GLib.timeout_add_seconds(4, self._poll_state)

    # ── App icon ─────────────────────────────────────────────────────────── #

    def _set_app_icon(self):
        pb = _svg_pixbuf("icon_app.svg", 48)
        if pb:
            self.set_icon(pb)

    # ── UI Construction ───────────────────────────────────────────────────── #

    def _build_ui(self):
        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("OpenVPN GUI")
        self.set_titlebar(header)

        import_btn = Gtk.Button()
        import_btn.set_tooltip_text("Import .ovpn config file")
        import_icon = Gtk.Image.new_from_icon_name("document-open-symbolic", Gtk.IconSize.BUTTON)
        import_btn.set_image(import_icon)
        import_btn.connect("clicked", self._on_import_clicked)
        import_btn.get_style_context().add_class("suggested-action")
        header.pack_end(import_btn)

        # Main paned
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(240)
        self.add(paned)

        paned.pack1(self._build_sidebar(), resize=False, shrink=False)
        paned.pack2(self._build_detail_panel(), resize=True, shrink=False)

    # ── Sidebar ───────────────────────────────────────────────────────────── #

    def _build_sidebar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.get_style_context().add_class("sidebar")
        box.set_size_request(220, -1)

        header = Gtk.Label(label="VPN PROFILES", xalign=0)
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

        # Empty state placeholder
        self._list_empty_label = Gtk.Label(label="No profiles yet.\nImport a .ovpn file.")
        self._list_empty_label.set_justify(Gtk.Justification.CENTER)
        self._list_empty_label.get_style_context().add_class("empty-panel-label")
        self._list_empty_label.set_margin_top(30)
        self._profile_list.set_placeholder(self._list_empty_label)

        scroll.add(self._profile_list)
        box.pack_start(scroll, True, True, 0)

        # Sidebar import button
        import_btn = Gtk.Button(label="+ Import Config")
        import_btn.get_style_context().add_class("import-sidebar-btn")
        import_btn.connect("clicked", self._on_import_clicked)
        box.pack_start(import_btn, False, False, 0)

        return box

    # ── Detail panel ─────────────────────────────────────────────────────── #

    def _build_detail_panel(self) -> Gtk.Widget:
        self._detail_stack = Gtk.Stack()
        self._detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._detail_stack.set_transition_duration(150)

        # ── Empty page ─────────────────────── #
        empty_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)

        empty_img = Gtk.Image.new_from_file(
            os.path.join(_ASSETS, "icon_disconnected.svg")
        )
        empty_img.set_pixel_size(64)
        empty_img.set_opacity(0.25)

        empty_lbl = Gtk.Label(
            label="Select a profile\nor import a new one."
        )
        empty_lbl.get_style_context().add_class("empty-panel-label")
        empty_lbl.set_justify(Gtk.Justification.CENTER)

        empty_box.pack_start(empty_img, False, False, 0)
        empty_box.pack_start(empty_lbl, False, False, 0)
        self._detail_stack.add_named(empty_box, "empty")

        # ── Connection page ────────────────── #
        conn_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        conn_outer.get_style_context().add_class("detail-panel")

        # Status row (icon + label)
        status_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=14
        )
        status_row.set_margin_bottom(20)

        self._status_image = Gtk.Image()
        self._status_image.set_pixel_size(52)
        status_row.pack_start(self._status_image, False, False, 0)

        status_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_vbox.set_valign(Gtk.Align.CENTER)

        self._profile_title = Gtk.Label(label="", xalign=0)
        self._profile_title.get_style_context().add_class("profile-title")
        self._profile_title.set_ellipsize(Pango.EllipsizeMode.END)

        self._server_label = Gtk.Label(label="", xalign=0)
        self._server_label.get_style_context().add_class("profile-server-label")
        self._server_label.set_ellipsize(Pango.EllipsizeMode.END)

        self._status_label = Gtk.Label(label="Disconnected", xalign=0)
        self._status_label.get_style_context().add_class("status-label-disconnected")

        status_vbox.pack_start(self._profile_title, False, False, 0)
        status_vbox.pack_start(self._server_label, False, False, 0)
        status_vbox.pack_start(self._status_label, False, False, 0)

        status_row.pack_start(status_vbox, True, True, 0)

        # Delete button (top-right)
        delete_btn = Gtk.Button()
        delete_btn.set_tooltip_text("Remove this profile")
        delete_icon = Gtk.Image.new_from_icon_name(
            "user-trash-symbolic", Gtk.IconSize.BUTTON
        )
        delete_btn.set_image(delete_icon)
        delete_btn.set_valign(Gtk.Align.START)
        delete_btn.get_style_context().add_class("destructive-action")
        delete_btn.connect("clicked", self._on_delete_profile)
        status_row.pack_end(delete_btn, False, False, 0)

        conn_outer.pack_start(status_row, False, False, 0)

        # Separator
        sep1 = Gtk.Separator()
        sep1.get_style_context().add_class("section-sep")
        conn_outer.pack_start(sep1, False, False, 0)

        # ── Credentials grid ──────────────── #
        cred_grid = Gtk.Grid()
        cred_grid.set_column_spacing(12)
        cred_grid.set_row_spacing(10)
        cred_grid.set_margin_bottom(6)

        # Username
        user_lbl = Gtk.Label(label="USERNAME", xalign=0)
        user_lbl.get_style_context().add_class("field-label")
        self._username_entry = Gtk.Entry()
        self._username_entry.set_placeholder_text("Enter username…")
        self._username_entry.get_style_context().add_class("field-entry")
        self._username_entry.set_hexpand(True)
        self._username_entry.connect("changed", self._on_credentials_changed)

        # Password
        pass_lbl = Gtk.Label(label="PASSWORD", xalign=0)
        pass_lbl.get_style_context().add_class("field-label")

        pass_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._password_entry = Gtk.Entry()
        self._password_entry.set_placeholder_text("Enter password…")
        self._password_entry.set_visibility(False)
        self._password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self._password_entry.get_style_context().add_class("field-entry")
        self._password_entry.set_hexpand(True)
        self._password_entry.connect("changed", self._on_credentials_changed)

        # Eye toggle for password visibility
        self._eye_btn = Gtk.ToggleButton()
        eye_img = Gtk.Image.new_from_icon_name(
            "view-reveal-symbolic", Gtk.IconSize.BUTTON
        )
        self._eye_btn.set_image(eye_img)
        self._eye_btn.set_tooltip_text("Show / hide password")
        self._eye_btn.connect("toggled", self._on_eye_toggled)
        self._eye_btn.get_style_context().add_class("flat")

        pass_box.pack_start(self._password_entry, True, True, 0)
        pass_box.pack_start(self._eye_btn, False, False, 0)

        cred_grid.attach(user_lbl, 0, 0, 1, 1)
        cred_grid.attach(self._username_entry, 0, 1, 1, 1)
        cred_grid.attach(pass_lbl, 0, 2, 1, 1)
        cred_grid.attach(pass_box, 0, 3, 1, 1)

        # Remember checkbox
        self._remember_check = Gtk.CheckButton(
            label="Remember credentials (stored in system keyring)"
        )
        self._remember_check.set_margin_top(6)
        self._remember_check.connect("toggled", self._on_remember_toggled)

        conn_outer.pack_start(cred_grid, False, False, 0)
        conn_outer.pack_start(self._remember_check, False, False, 0)

        # Separator
        sep2 = Gtk.Separator()
        sep2.get_style_context().add_class("section-sep")
        conn_outer.pack_start(sep2, False, False, 0)

        # ── Connect button ────────────────── #
        self._connect_btn = Gtk.Button(label="CONNECT")
        self._connect_btn.get_style_context().add_class("suggested-action")
        self._connect_btn.get_style_context().add_class("connect-btn")
        self._connect_btn.connect("clicked", self._on_connect_clicked)

        # Spinner (shown while connecting)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(20, 20)
        self._spinner.set_no_show_all(True)

        self._conn_btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10
        )
        self._conn_btn_box.set_homogeneous(False)
        self._conn_btn_box.pack_start(self._spinner, False, False, 0)
        self._conn_btn_box.pack_start(self._connect_btn, True, True, 0)

        conn_outer.pack_end(self._conn_btn_box, False, False, 0)

        self._detail_stack.add_named(conn_outer, "connection")
        self._detail_stack.set_visible_child_name("empty")

        return self._detail_stack

    # ── Profile management ────────────────────────────────────────────────── #

    def _refresh_profiles(self):
        """Reload all VPN profiles from NetworkManager and rebuild the list."""
        profiles = self._vpn.get_profiles()

        # Clear existing rows
        for row in self._profile_list.get_children():
            self._profile_list.remove(row)

        for profile in profiles:
            row = ProfileRow(profile)
            # Load server info in background
            self._profile_list.add(row)
            threading.Thread(
                target=self._load_server_for_row,
                args=(row, profile["name"]),
                daemon=True,
            ).start()

        self._profile_list.show_all()

        # Re-select last known profile
        last = config.get("last_selected_profile")
        if last:
            for row in self._profile_list.get_children():
                if isinstance(row, ProfileRow) and row.profile["name"] == last:
                    self._profile_list.select_row(row)
                    break

    def _load_server_for_row(self, row: ProfileRow, profile_name: str):
        server = self._vpn.get_server(profile_name)
        GLib.idle_add(row.set_server, server)

    def _on_profile_selected(self, listbox, row):
        if not isinstance(row, ProfileRow):
            self._selected_profile = None
            self._detail_stack.set_visible_child_name("empty")
            return

        profile = row.profile
        self._selected_profile = profile["name"]
        config.set_value("last_selected_profile", profile["name"])

        # Update detail panel
        self._profile_title.set_text(profile["name"])
        self._update_detail_state(profile["connected"])

        # Load credentials
        has_saved = config.has_saved_creds(profile["name"])
        if has_saved:
            username, password = cred_store.load(profile["name"])
            self._username_entry.set_text(username)
            self._password_entry.set_text(password)
            self._remember_check.set_active(True)
        else:
            self._username_entry.set_text("")
            self._password_entry.set_text("")
            self._remember_check.set_active(False)

        # Load server label
        server = self._vpn.get_server(profile["name"])
        self._server_label.set_text(server)

        self._detail_stack.set_visible_child_name("connection")

    def _update_detail_state(self, connected: bool, busy: bool = False):
        """Update status icon, label and connect button for the given state."""
        sc_status = self._status_label.get_style_context()
        for cls in ("status-label-connected", "status-label-disconnected", "status-label-busy"):
            sc_status.remove_class(cls)

        sc_btn = self._connect_btn.get_style_context()
        for cls in ("suggested-action", "destructive-action"):
            sc_btn.remove_class(cls)

        if busy:
            self._status_label.set_text(
                "Connecting…" if not connected else "Disconnecting…"
            )
            sc_status.add_class("status-label-busy")
            self._connect_btn.set_sensitive(False)
            self._spinner.show()
            self._spinner.start()
            pb = _svg_pixbuf("icon_disconnected.svg", 52)
        elif connected:
            self._status_label.set_text("Connected")
            sc_status.add_class("status-label-connected")
            self._connect_btn.set_label("DISCONNECT")
            sc_btn.add_class("destructive-action")
            self._connect_btn.set_sensitive(True)
            self._spinner.hide()
            self._spinner.stop()
            pb = _svg_pixbuf("icon_connected.svg", 52)
        else:
            self._status_label.set_text("Disconnected")
            sc_status.add_class("status-label-disconnected")
            self._connect_btn.set_label("CONNECT")
            sc_btn.add_class("suggested-action")
            self._connect_btn.set_sensitive(True)
            self._spinner.hide()
            self._spinner.stop()
            pb = _svg_pixbuf("icon_disconnected.svg", 52)

        if pb:
            self._status_image.set_from_pixbuf(pb)

    # ── Import ────────────────────────────────────────────────────────────── #

    def _on_import_clicked(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title="Import OpenVPN Config",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Import", Gtk.ResponseType.OK,
        )
        dialog.set_default_response(Gtk.ResponseType.OK)

        ovpn_filter = Gtk.FileFilter()
        ovpn_filter.set_name("OpenVPN Config (*.ovpn)")
        ovpn_filter.add_pattern("*.ovpn")
        dialog.add_filter(ovpn_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
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
            self._show_info("Profile imported", f'"{result}" has been added.')
            self._refresh_profiles()
            # Auto-select the new profile
            for row in self._profile_list.get_children():
                if isinstance(row, ProfileRow) and row.profile["name"] == result:
                    self._profile_list.select_row(row)
                    break
        else:
            self._show_error("Import failed", result)

    # ── Delete profile ────────────────────────────────────────────────────── #

    def _on_delete_profile(self, _btn):
        if not self._selected_profile:
            return

        name = self._selected_profile
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f'Delete "{name}"?',
        )
        dialog.format_secondary_text(
            "This will remove the profile from NetworkManager.\n"
            "Saved credentials will also be deleted."
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        delete_btn = dialog.add_button("_Delete", Gtk.ResponseType.OK)
        delete_btn.get_style_context().add_class("destructive-action")

        if dialog.run() == Gtk.ResponseType.OK:
            dialog.destroy()
            ok, msg = self._vpn.delete_profile(name)
            if ok:
                cred_store.delete(name)
                config.unmark_creds_saved(name)
                self._selected_profile = None
                self._detail_stack.set_visible_child_name("empty")
                self._refresh_profiles()
            else:
                self._show_error("Delete failed", msg)
        else:
            dialog.destroy()

    # ── Connect / Disconnect ─────────────────────────────────────────────── #

    def _on_connect_clicked(self, _btn):
        if not self._selected_profile:
            return
        if self._state != self._STATE_IDLE:
            return

        connected = self._vpn.is_connected(self._selected_profile)
        if connected:
            self._start_disconnect()
        else:
            self._start_connect()

    def _start_connect(self):
        profile = self._selected_profile
        username = self._username_entry.get_text().strip()
        password = self._password_entry.get_text()

        # Save credentials if requested
        if self._remember_check.get_active() and (username or password):
            cred_store.save(profile, username, password)
            config.mark_creds_saved(profile)
        elif not self._remember_check.get_active():
            cred_store.delete(profile)
            config.unmark_creds_saved(profile)

        self._state = self._STATE_CONNECTING
        self._update_detail_state(connected=False, busy=True)
        self._tray.set_connected(False)

        threading.Thread(
            target=self._bg_connect,
            args=(profile, username, password),
            daemon=True,
        ).start()

    def _bg_connect(self, profile: str, username: str, password: str):
        ok, msg = self._vpn.connect(profile, username, password)
        GLib.idle_add(self._on_connect_done, ok, msg, profile)

    def _on_connect_done(self, ok: bool, msg: str, profile: str):
        self._state = self._STATE_IDLE
        if ok:
            self._update_detail_state(connected=True)
            self._tray.set_connected(True, profile)
            self._refresh_sidebar_dots()
        else:
            self._update_detail_state(connected=False)
            self._tray.set_connected(False)
            self._show_error("Connection failed", msg)
        return False  # remove GLib source

    def _start_disconnect(self):
        profile = self._selected_profile
        self._state = self._STATE_DISCONNECTING
        self._update_detail_state(connected=True, busy=True)

        threading.Thread(
            target=self._bg_disconnect,
            args=(profile,),
            daemon=True,
        ).start()

    def _bg_disconnect(self, profile: str):
        ok, msg = self._vpn.disconnect(profile)
        GLib.idle_add(self._on_disconnect_done, ok, msg)

    def _on_disconnect_done(self, ok: bool, msg: str):
        self._state = self._STATE_IDLE
        self._update_detail_state(connected=False)
        self._tray.set_connected(False)
        self._refresh_sidebar_dots()
        if not ok:
            self._show_error("Disconnect failed", msg)
        return False

    # Called from TrayIcon menu "Connect/Disconnect"
    def toggle_connection(self):
        if self._selected_profile and self._state == self._STATE_IDLE:
            connected = self._vpn.is_connected(self._selected_profile)
            if connected:
                self._start_disconnect()
            else:
                self._start_connect()

    # ── Polling ───────────────────────────────────────────────────────────── #

    def _poll_state(self) -> bool:
        if self._state != self._STATE_IDLE:
            return True  # skip while busy

        profiles = self._vpn.get_profiles()
        any_connected = False
        connected_name = ""

        for profile in profiles:
            if profile["connected"]:
                any_connected = True
                connected_name = profile["name"]
                break

        # Update tray
        self._tray.set_connected(any_connected, connected_name)

        # Update selected profile detail if it changed
        if self._selected_profile:
            is_now = self._vpn.is_connected(self._selected_profile)
            self._update_detail_state(is_now)

        self._refresh_sidebar_dots(profiles)
        return True  # keep polling

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

    def _on_credentials_changed(self, _entry):
        pass  # Could add real-time validation here

    def _on_remember_toggled(self, btn):
        if not btn.get_active() and self._selected_profile:
            # Immediately purge if unchecked
            cred_store.delete(self._selected_profile)
            config.unmark_creds_saved(self._selected_profile)

    def _on_eye_toggled(self, btn):
        self._password_entry.set_visibility(btn.get_active())

    # ── Window hide / show ────────────────────────────────────────────────── #

    def _on_delete(self, _widget, _event):
        if config.get("minimize_to_tray"):
            self.hide()
            return True  # Prevent destroy
        return False  # Allow destroy → Gtk.main_quit

    def show_and_raise(self):
        self.show_all()
        self.present()
        # Force the window to the top on X11/Cinnamon (focus-stealing prevention
        # can block present() alone).
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.raise_()
            gdk_win.focus(Gdk.CURRENT_TIME)

    # ── Dialogs ───────────────────────────────────────────────────────────── #

    def _show_info(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()

    def _show_error(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()
