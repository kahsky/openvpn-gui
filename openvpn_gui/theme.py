"""
Dukiwi visual theme — colour palette + application-wide GTK CSS.

Primary brand colour: #013861 (Dukiwi navy).  All accents are derived
from the same family so the app reads as one blue system in both the
light and dark GTK themes.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

# ── Palette ────────────────────────────────────────────────────────────────── #
NAVY = "#013861"        # primary
NAVY_DARK = "#012744"
NAVY_DEEP = "#011E3A"
NAVY_LIGHT = "#0A5A8F"
BLUE = "#0a84d0"        # accent / connected
BLUE_LIGHT = "#4db8ff"
BLUE_PALE = "#e8f4fd"
GREY = "#8FA3B5"        # disconnected
RED = "#E05A5A"
AMBER = "#F0A848"


def rgb(hexstr: str):
    """'#RRGGBB' → (r, g, b) floats in 0..1."""
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def is_dark_theme(widget: Gtk.Widget = None) -> bool:
    """Best-effort detection of a dark GTK theme (from theme_bg_color)."""
    ctx = (widget or Gtk.Window()).get_style_context()
    ok, color = ctx.lookup_color("theme_bg_color")
    if not ok:
        return False
    lum = 0.2126 * color.red + 0.7152 * color.green + 0.0722 * color.blue
    return lum < 0.5


# ── CSS ────────────────────────────────────────────────────────────────────── #
CSS = f"""
@define-color dk_navy {NAVY};
@define-color dk_navy_dark {NAVY_DARK};
@define-color dk_navy_deep {NAVY_DEEP};
@define-color dk_navy_light {NAVY_LIGHT};
@define-color dk_blue {BLUE};
@define-color dk_blue_light {BLUE_LIGHT};
@define-color dk_grey {GREY};
@define-color dk_red {RED};
@define-color dk_amber {AMBER};

@keyframes dk-pulse {{
    0%   {{ opacity: 1; }}
    50%  {{ opacity: 0.35; }}
    100% {{ opacity: 1; }}
}}

/* ── Header bar ─────────────────────────────────────────────────────── */
headerbar.dk-header {{
    background-image: linear-gradient(to right, @dk_navy, @dk_navy_light);
    background-color: @dk_navy;
    color: white;
    border-bottom: 1px solid @dk_navy_dark;
    box-shadow: none;
    text-shadow: none;
}}
headerbar.dk-header .title    {{ color: white; font-weight: bold; }}
headerbar.dk-header .subtitle {{ color: alpha(white, 0.75); }}
headerbar.dk-header button {{
    color: white;
    background-image: none;
    background-color: alpha(white, 0.12);
    border: 1px solid alpha(white, 0.18);
    box-shadow: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
}}
headerbar.dk-header button:hover  {{ background-color: alpha(white, 0.24); }}
headerbar.dk-header button:active {{ background-color: alpha(white, 0.32); }}
headerbar.dk-header button.titlebutton {{
    background-color: transparent;
    border: none;
}}
headerbar.dk-header button.titlebutton:hover {{ background-color: alpha(white, 0.2); }}

/* ── Sidebar ────────────────────────────────────────────────────────── */
.sidebar {{
    background-color: @dk_navy_dark;
    border-right: 1px solid @dk_navy_deep;
}}
.sidebar-header {{
    padding: 16px 16px 8px 16px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.5px;
    color: alpha(white, 0.55);
}}
.profile-list {{ background-color: transparent; }}
.profile-list row {{
    padding: 10px 14px;
    color: white;
    border-left: 3px solid transparent;
    background-color: transparent;
}}
.profile-list row:hover {{ background-color: alpha(white, 0.06); }}
.profile-list row:selected {{
    background-color: alpha(white, 0.12);
    border-left: 3px solid @dk_blue_light;
    color: white;
}}
.profile-row-name   {{ font-size: 13px; font-weight: bold; color: white; }}
.profile-row-server {{ font-size: 11px; color: alpha(white, 0.6); }}
.dot {{
    min-width: 9px;
    min-height: 9px;
    border-radius: 5px;
    margin-right: 10px;
    margin-top: 4px;
    background-color: alpha(white, 0.25);
}}
.dot-connected    {{ background-color: @dk_blue_light; }}
.dot-connecting   {{ background-color: @dk_blue_light; animation: dk-pulse 1s ease-in-out infinite; }}
.dot-disconnected {{ background-color: alpha(white, 0.25); }}
.sidebar-btn {{
    margin: 4px 10px 0 10px;
    padding: 7px 0;
    color: white;
    background-image: none;
    background-color: alpha(white, 0.10);
    border: 1px solid alpha(white, 0.15);
    border-radius: 6px;
    box-shadow: none;
    text-shadow: none;
}}
.sidebar-btn:hover {{ background-color: alpha(white, 0.2); }}
.sidebar-footer {{
    padding: 10px 14px 12px 14px;
    color: alpha(white, 0.5);
    font-size: 10px;
}}
.empty-list-label {{ color: alpha(white, 0.45); font-size: 12px; }}

/* ── Detail panel ───────────────────────────────────────────────────── */
.detail-panel {{ padding: 24px 28px 20px 28px; }}
.empty-panel-label {{ color: alpha(@theme_fg_color, 0.45); font-size: 14px; }}
.profile-title {{ font-size: 21px; font-weight: bold; }}
.profile-server-label {{ font-size: 12px; color: alpha(@theme_fg_color, 0.6); }}
.status-label {{ font-size: 13px; font-weight: bold; }}
.status-connected    {{ color: @dk_blue; }}
.status-disconnected {{ color: @dk_grey; }}
.status-busy         {{ color: @dk_blue_light; }}
.status-error        {{ color: @dk_red; }}
.section-sep {{ margin-top: 14px; margin-bottom: 14px; }}
.section-title {{
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1.5px;
    color: alpha(@theme_fg_color, 0.5);
    margin-bottom: 2px;
}}
.field-label {{
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    color: alpha(@theme_fg_color, 0.6);
    margin-bottom: 3px;
}}
.field-entry {{ padding: 6px 10px; border-radius: 6px; }}
.field-entry:focus {{ border-color: @dk_blue; }}
.hint-label {{ font-size: 11px; color: alpha(@theme_fg_color, 0.5); }}

/* Primary action button */
.connect-btn {{
    padding: 12px 0;
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 1px;
    border-radius: 8px;
    margin-top: 6px;
    color: white;
    background-image: none;
    background-color: @dk_navy;
    border: 1px solid @dk_navy_dark;
    box-shadow: none;
    text-shadow: none;
}}
.connect-btn:hover  {{ background-color: @dk_navy_light; }}
.connect-btn:active {{ background-color: @dk_navy_dark; }}
.connect-btn:disabled {{ color: alpha(white, 0.6); background-color: alpha(@dk_navy, 0.5); }}
.connect-btn.secondary {{
    color: @theme_fg_color;
    background-color: alpha(@dk_blue, 0.12);
    border: 1px solid alpha(@dk_blue, 0.55);
}}
.connect-btn.secondary:hover {{ background-color: alpha(@dk_blue, 0.22); }}
.connect-btn.secondary:disabled {{ color: alpha(@theme_fg_color, 0.5); }}

/* Flat "see more" toggle */
.more-btn {{
    padding: 4px 12px;
    border-radius: 14px;
    color: @dk_blue;
    background-image: none;
    background-color: alpha(@dk_blue, 0.08);
    border: 1px solid alpha(@dk_blue, 0.3);
    box-shadow: none;
    font-size: 12px;
}}
.more-btn:hover, .more-btn:checked {{ background-color: alpha(@dk_blue, 0.18); }}

/* Cards */
.card {{
    background-color: alpha(@theme_fg_color, 0.035);
    border: 1px solid alpha(@theme_fg_color, 0.09);
    border-radius: 12px;
    padding: 16px 18px;
}}
.card-blue {{
    background-color: alpha(@dk_blue, 0.07);
    border: 1px solid alpha(@dk_blue, 0.25);
}}
.stat-label {{
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1.5px;
    color: alpha(@theme_fg_color, 0.55);
}}
.stat-value {{ font-size: 24px; font-weight: bold; color: @dk_blue; }}
.stat-value-up {{ color: @dk_blue_light; }}
.stat-sub {{ font-size: 11px; color: alpha(@theme_fg_color, 0.6); }}
.info-chip {{
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 10px;
    background-color: alpha(@dk_blue, 0.1);
    border: 1px solid alpha(@dk_blue, 0.25);
    color: @theme_fg_color;
}}
.connecting-title {{ font-size: 17px; font-weight: bold; }}
.connecting-detail {{ font-size: 11px; color: alpha(@theme_fg_color, 0.55); font-family: monospace; }}

/* Verbose log */
.log-frame {{
    border: 1px solid alpha(@dk_navy, 0.35);
    border-radius: 8px;
    background-color: @dk_navy_deep;
}}
.log-toolbar {{
    padding: 4px 8px 4px 12px;
    background-color: alpha(white, 0.05);
    border-bottom: 1px solid alpha(white, 0.08);
    color: alpha(white, 0.7);
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1.5px;
}}
.log-toolbar button {{
    color: alpha(white, 0.8);
    background-image: none;
    background-color: transparent;
    border: none;
    box-shadow: none;
    padding: 2px 6px;
    min-height: 0;
}}
.log-toolbar button:hover {{ background-color: alpha(white, 0.1); }}
textview.log-view, textview.log-view text {{
    background-color: @dk_navy_deep;
    color: #CFE6F7;
    font-family: monospace;
    font-size: 11px;
}}
infobar.dk-error, infobar.dk-error > revealer > box {{
    background-color: alpha(@dk_red, 0.12);
    border: 1px solid alpha(@dk_red, 0.4);
    border-radius: 8px;
    color: @theme_fg_color;
}}
"""


def apply_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
