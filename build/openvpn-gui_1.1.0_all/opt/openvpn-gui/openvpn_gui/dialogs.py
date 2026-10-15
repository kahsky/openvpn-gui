"""
Dialogs: manual profile creation and the About box.
"""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

from . import __version__, __app_name__
from .i18n import _
from . import theme
from .vpn_manager import DEFAULT_PORT

_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)


def _label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.get_style_context().add_class("field-label")
    return lbl


class ManualProfileDialog(Gtk.Dialog):
    """Create an OpenVPN profile by hand: host, port, protocol, CA, credentials."""

    def __init__(self, parent: Gtk.Window, existing_names=()):
        super().__init__(title=_("New manual profile"), transient_for=parent, modal=True)
        self._existing = {n.lower() for n in existing_names}
        self.set_default_size(460, -1)
        self.set_resizable(False)

        self.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        self._create_btn = self.add_button(_("C_reate"), Gtk.ResponseType.OK)
        self._create_btn.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(16)
        box.set_margin_bottom(8)
        box.set_margin_start(20)
        box.set_margin_end(20)

        intro = Gtk.Label(
            label=_("Define the server yourself — no .ovpn file needed.\n"
                    "Credentials are asked at connection time or saved in the system keyring."),
            xalign=0,
        )
        intro.get_style_context().add_class("hint-label")
        intro.set_line_wrap(True)
        box.pack_start(intro, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_top(10)
        box.pack_start(grid, False, False, 0)

        row = 0
        # Name
        grid.attach(_label(_("PROFILE NAME")), 0, row, 3, 1); row += 1
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text(_("e.g. Office VPN"))
        self.name_entry.get_style_context().add_class("field-entry")
        self.name_entry.set_hexpand(True)
        self.name_entry.set_activates_default(True)
        grid.attach(self.name_entry, 0, row, 3, 1); row += 1

        # Host / port / proto
        grid.attach(_label(_("HOST")), 0, row, 1, 1)
        grid.attach(_label(_("PORT")), 1, row, 1, 1)
        grid.attach(_label(_("PROTOCOL")), 2, row, 1, 1); row += 1
        self.host_entry = Gtk.Entry()
        self.host_entry.set_placeholder_text("vpn.example.com")
        self.host_entry.get_style_context().add_class("field-entry")
        self.host_entry.set_hexpand(True)
        self.host_entry.set_activates_default(True)
        grid.attach(self.host_entry, 0, row, 1, 1)
        self.port_spin = Gtk.SpinButton.new_with_range(1, 65535, 1)
        self.port_spin.set_value(DEFAULT_PORT)
        self.port_spin.set_tooltip_text(_("OpenVPN default: 1194"))
        self.port_spin.get_style_context().add_class("field-entry")
        grid.attach(self.port_spin, 1, row, 1, 1)
        self.proto_combo = Gtk.ComboBoxText()
        self.proto_combo.append("udp", "UDP")
        self.proto_combo.append("tcp", "TCP")
        self.proto_combo.set_active_id("udp")
        grid.attach(self.proto_combo, 2, row, 1, 1); row += 1

        # CA
        grid.attach(_label(_("CA CERTIFICATE")), 0, row, 3, 1); row += 1
        self.ca_chooser = Gtk.FileChooserButton(title=_("Select CA certificate"))
        self.ca_chooser.set_hexpand(True)
        flt = Gtk.FileFilter()
        flt.set_name(_("Certificates (*.crt, *.pem, *.cer)"))
        for pat in ("*.crt", "*.pem", "*.cer", "*.CRT", "*.PEM"):
            flt.add_pattern(pat)
        self.ca_chooser.add_filter(flt)
        allf = Gtk.FileFilter()
        allf.set_name(_("All files"))
        allf.add_pattern("*")
        self.ca_chooser.add_filter(allf)
        grid.attach(self.ca_chooser, 0, row, 3, 1); row += 1
        ca_hint = Gtk.Label(
            label=_("Optional here, but nearly every server requires it "
                    "(OpenVPN refuses to start without a CA)."),
            xalign=0,
        )
        ca_hint.get_style_context().add_class("hint-label")
        ca_hint.set_line_wrap(True)
        grid.attach(ca_hint, 0, row, 3, 1); row += 1

        # Credentials
        grid.attach(_label(_("USERNAME")), 0, row, 3, 1); row += 1
        self.user_entry = Gtk.Entry()
        self.user_entry.set_placeholder_text(_("Enter username…"))
        self.user_entry.get_style_context().add_class("field-entry")
        self.user_entry.set_activates_default(True)
        grid.attach(self.user_entry, 0, row, 3, 1); row += 1

        grid.attach(_label(_("PASSWORD")), 0, row, 3, 1); row += 1
        pbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.pass_entry = Gtk.Entry()
        self.pass_entry.set_placeholder_text(_("Enter password…"))
        self.pass_entry.set_visibility(False)
        self.pass_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.pass_entry.get_style_context().add_class("field-entry")
        self.pass_entry.set_hexpand(True)
        self.pass_entry.set_activates_default(True)
        eye = Gtk.ToggleButton()
        eye.set_image(Gtk.Image.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.BUTTON))
        eye.get_style_context().add_class("flat")
        eye.connect("toggled", lambda b: self.pass_entry.set_visibility(b.get_active()))
        pbox.pack_start(self.pass_entry, True, True, 0)
        pbox.pack_start(eye, False, False, 0)
        grid.attach(pbox, 0, row, 3, 1); row += 1

        self.remember_check = Gtk.CheckButton(label=_("Remember credentials (stored in system keyring)"))
        self.remember_check.set_margin_top(4)
        grid.attach(self.remember_check, 0, row, 3, 1); row += 1

        self._error = Gtk.Label(label="", xalign=0)
        self._error.get_style_context().add_class("status-error")
        self._error.set_line_wrap(True)
        self._error.set_no_show_all(True)
        box.pack_start(self._error, False, False, 4)

        for w in (self.name_entry, self.host_entry):
            w.connect("changed", self._validate)
        self._validate()
        self.show_all()

    def _validate(self, *_a):
        name = self.name_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        ok = bool(name) and bool(host) and not any(c.isspace() for c in host)
        msg = ""
        if name and name.lower() in self._existing:
            ok = False
            msg = _("A profile with this name already exists.")
        self._create_btn.set_sensitive(ok)
        if msg:
            self._error.set_text(msg)
            self._error.show()
        else:
            self._error.hide()

    def show_error(self, msg: str):
        self._error.set_text(msg)
        self._error.show()

    def get_values(self) -> dict:
        return {
            "name": self.name_entry.get_text().strip(),
            "host": self.host_entry.get_text().strip(),
            "port": int(self.port_spin.get_value()),
            "proto": self.proto_combo.get_active_id() or "udp",
            "ca": self.ca_chooser.get_filename() or "",
            "username": self.user_entry.get_text().strip(),
            "password": self.pass_entry.get_text(),
            "remember": self.remember_check.get_active(),
        }


def show_about(parent: Gtk.Window) -> None:
    """About box crediting Dukiwi, the creator of this GUI."""
    from .widgets import recolored_logo_pixbuf

    dlg = Gtk.AboutDialog(transient_for=parent, modal=True)
    dlg.set_program_name(__app_name__)
    dlg.set_version(__version__)
    dlg.set_comments(
        _("A modern OpenVPN client for Linux Mint / Ubuntu.\n"
          "Application created by Dukiwi.")
    )
    dlg.set_website("https://dukiwi.com")
    dlg.set_website_label("dukiwi.com")
    dlg.set_copyright("© 2026 Dukiwi")
    dlg.set_license_type(Gtk.License.GPL_3_0)
    dlg.set_authors(["Dukiwi"])
    color = (1, 1, 1, 0.95) if theme.is_dark_theme(parent) else (*theme.rgb(theme.NAVY), 1)
    logo = recolored_logo_pixbuf(color, height=56)
    if logo:
        dlg.set_logo(logo)
    else:
        try:
            dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
                os.path.join(_ASSETS, "icon_app.svg"), 64, 64))
        except Exception:
            pass
    dlg.run()
    dlg.destroy()
