"""Entry point — run with:  python -m openvpn_gui  or via the 'openvpn-gui' script."""
import sys


def main():
    # GTK requires the GLib main loop; importing GLib here ensures
    # threads are set up correctly before creating the Gtk.Application.
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib
    GLib.set_prgname("openvpn-gui")
    GLib.set_application_name("OpenVPN GUI")

    from .app import OpenVPNApp
    app = OpenVPNApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
