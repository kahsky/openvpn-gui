"""
Custom widgets (cairo-drawn) used by the main window.

  ConnectAnimation — sonar rings + comet arc around a breathing shield
  StepIndicator    — 4-step progress line (prepare → auth → tunnel → network)
  TrafficGraph     — live download / upload sparkline area chart
  LogView          — verbose connection log (monospace, colour-tagged)
  LogoWidget       — Dukiwi word-mark painted in any colour through its alpha
"""
import math
import os
import time
from collections import deque
from typing import List, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango, PangoCairo

from .i18n import _
from . import theme

_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)


# ── Formatting helpers ─────────────────────────────────────────────────────── #

def format_bytes(n: float, per_second: bool = False) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(max(n, 0))
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    s = f"{v:.0f}" if i == 0 else (f"{v:.1f}" if v < 100 else f"{v:.0f}")
    s = f"{s} {units[i]}"
    return s + "/s" if per_second else s


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fg_rgba(widget: Gtk.Widget):
    c = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
    return (c.red, c.green, c.blue)


def _nice_ceiling(value: float) -> float:
    """Round a byte rate up to a 'nice' value (1, 2, 5 × 1024^k)."""
    if value <= 0:
        return 10 * 1024.0
    unit = 1.0
    v = value
    while v >= 1024 and unit < 1024 ** 4:
        v /= 1024.0
        unit *= 1024.0
    for nice in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
        if v <= nice:
            return nice * unit
    return 1024 * unit


# ── Logo ───────────────────────────────────────────────────────────────────── #

class LogoWidget(Gtk.DrawingArea):
    """Paints the Dukiwi PNG word-mark as a mask in the given colour."""

    def __init__(self, height: int = 20, color=(1, 1, 1, 0.85),
                 filename: str = "logo_dukiwi.png"):
        super().__init__()
        self._color = color
        self._h = height
        path = os.path.join(_ASSETS, filename)
        try:
            self._pb = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:
            self._pb = None
        if self._pb:
            w = int(self._pb.get_width() * height / self._pb.get_height())
            self.set_size_request(w, height)
        self.connect("draw", self._on_draw)

    def set_color(self, color):
        self._color = color
        self.queue_draw()

    def _on_draw(self, _w, cr):
        if not self._pb:
            return False
        alloc_w = self.get_allocated_width()
        alloc_h = self.get_allocated_height()
        scale = self._h / self._pb.get_height()
        w = self._pb.get_width() * scale
        cr.translate((alloc_w - w) / 2, (alloc_h - self._h) / 2)
        cr.scale(scale, scale)
        cr.set_source_rgba(*self._color)
        surface = Gdk.cairo_surface_create_from_pixbuf(self._pb, 1, self.get_window())
        cr.mask_surface(surface, 0, 0)
        return False


def recolored_logo_pixbuf(color=(1, 1, 1, 1), height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
    """Return the Dukiwi logo as a pixbuf painted in `color` (for dialogs)."""
    import cairo
    path = os.path.join(_ASSETS, "logo_dukiwi.png")
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
    except Exception:
        return None
    scale = height / pb.get_height()
    w = int(pb.get_width() * scale)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, height)
    cr = cairo.Context(surface)
    cr.scale(scale, scale)
    cr.set_source_rgba(*color)
    src = Gdk.cairo_surface_create_from_pixbuf(pb, 1, None)
    cr.mask_surface(src, 0, 0)
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, height)


# ── Connect animation ──────────────────────────────────────────────────────── #

class ConnectAnimation(Gtk.DrawingArea):
    """Sonar rings + rotating comet arc around a gently breathing shield."""

    def __init__(self, size: int = 190):
        super().__init__()
        self._size = size
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self._tick_id = None
        self._t0 = None
        self._t = 0.0
        self._mode = "connecting"      # connecting | success | failed
        self._mode_t = 0.0
        self._pb_cache = {}
        self.connect("draw", self._on_draw)
        self.connect("unmap", lambda *_: self.stop())

    # -- lifecycle ------------------------------------------------------- #

    def start(self, mode: str = "connecting"):
        self._mode = mode
        self._mode_t = self._t
        if self._tick_id is None:
            self._t0 = None
            self._tick_id = self.add_tick_callback(self._on_tick)

    def stop(self):
        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None

    def set_mode(self, mode: str):
        self._mode = mode
        self._mode_t = self._t
        self.queue_draw()

    def _on_tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        if self._t0 is None:
            self._t0 = now
        self._t = now - self._t0
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    # -- drawing --------------------------------------------------------- #

    def _shield(self, name: str, logical: int) -> Optional[GdkPixbuf.Pixbuf]:
        sf = self.get_scale_factor()
        key = (name, logical, sf)
        if key not in self._pb_cache:
            path = os.path.join(_ASSETS, name)
            try:
                self._pb_cache[key] = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    path, logical * sf, logical * sf
                )
            except Exception:
                self._pb_cache[key] = None
        return self._pb_cache[key]

    def _on_draw(self, _w, cr):
        W = self.get_allocated_width()
        H = self.get_allocated_height()
        cx, cy = W / 2.0, H / 2.0
        R = min(W, H) / 2.0
        t = self._t
        fg = _fg_rgba(self)
        blue = theme.rgb(theme.BLUE)
        blue_l = theme.rgb(theme.BLUE_LIGHT)
        red = theme.rgb(theme.RED)

        mode = self._mode
        mt = t - self._mode_t   # time since mode change

        # Sonar rings (expanding, fading)
        if mode == "connecting":
            for k in range(3):
                phase = ((t / 2.4) + k / 3.0) % 1.0
                r = R * 0.30 + (R * 0.97 - R * 0.30) * phase
                a = (1.0 - phase) ** 1.6 * 0.5
                cr.set_source_rgba(*blue, a)
                cr.set_line_width(2.0)
                cr.arc(cx, cy, r, 0, 2 * math.pi)
                cr.stroke()
        elif mode == "success":
            # one final ring bursts outwards, then a steady halo
            phase = min(mt / 0.9, 1.0)
            r = R * 0.30 + (R * 0.97 - R * 0.30) * phase
            cr.set_source_rgba(*blue, (1.0 - phase) * 0.6)
            cr.set_line_width(3.0)
            cr.arc(cx, cy, r, 0, 2 * math.pi)
            cr.stroke()
            cr.set_source_rgba(*blue, 0.10 + 0.05 * math.sin(t * 2.0))
            cr.arc(cx, cy, R * 0.55, 0, 2 * math.pi)
            cr.fill()
        elif mode == "failed":
            cr.set_source_rgba(*red, 0.12)
            cr.arc(cx, cy, R * 0.55, 0, 2 * math.pi)
            cr.fill()

        # Track ring
        track_r = R * 0.50
        cr.set_source_rgba(*fg, 0.10)
        cr.set_line_width(1.5)
        cr.arc(cx, cy, track_r, 0, 2 * math.pi)
        cr.stroke()

        # Comet arc (rotating, with fading trail)
        if mode == "connecting":
            base = (t / 1.5 % 1.0) * 2 * math.pi
            segs = 22
            span = math.radians(130)
            cr.set_line_cap(1)  # ROUND
            for i in range(segs):
                a1 = base - span * i / segs
                a0 = base - span * (i + 1) / segs
                alpha = (1.0 - i / segs) ** 1.4
                col = blue_l if i < 4 else blue
                cr.set_source_rgba(*col, alpha)
                cr.set_line_width(4.5)
                cr.arc(cx, cy, track_r, a0, a1 + 0.03)
                cr.stroke()
        elif mode == "success":
            # closing ring sweep
            frac = min(mt / 0.6, 1.0)
            cr.set_source_rgba(*blue, 0.9)
            cr.set_line_width(4.5)
            cr.set_line_cap(1)
            cr.arc(cx, cy, track_r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * frac)
            cr.stroke()
        elif mode == "failed":
            cr.set_source_rgba(*red, 0.8)
            cr.set_line_width(4.5)
            cr.arc(cx, cy, track_r, 0, 2 * math.pi)
            cr.stroke()

        # Shield (breathing)
        if mode == "connecting":
            s = 1.0 + 0.045 * math.sin(t * 2.4)
            name = "icon_connecting.svg"
        elif mode == "success":
            s = 1.0 + 0.18 * math.sin(min(mt, 0.5) / 0.5 * math.pi) * (1 if mt < 0.5 else 0)
            name = "icon_connected.svg"
        else:
            shake = math.sin(mt * 40) * max(0.0, 1.0 - mt / 0.5) * 4
            cr.translate(shake, 0)
            s = 1.0
            name = "icon_disconnected.svg"

        logical = int(R * 0.62)
        pb = self._shield(name, logical)
        if pb:
            sf = self.get_scale_factor()
            pw, ph = pb.get_width() / sf, pb.get_height() / sf
            cr.save()
            cr.translate(cx, cy)
            cr.scale(s / sf, s / sf)
            Gdk.cairo_set_source_pixbuf(cr, pb, -pw * sf / 2, -ph * sf / 2)
            cr.paint()
            cr.restore()
        return False


# ── Step indicator ─────────────────────────────────────────────────────────── #

class StepIndicator(Gtk.DrawingArea):
    """Horizontal step line: ●──●──○──○ with labels underneath."""

    def __init__(self, steps: List[str]):
        super().__init__()
        self._steps = steps
        self._current = 0
        self._failed = False
        self._done_all = False
        self._tick_id = None
        self._t = 0.0
        self.set_size_request(380, 58)
        self.set_hexpand(True)
        self.connect("draw", self._on_draw)
        self.connect("unmap", lambda *_: self.stop())

    def start(self):
        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._on_tick)

    def stop(self):
        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None

    def _on_tick(self, _w, clock):
        self._t = clock.get_frame_time() / 1e6
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def reset(self):
        self._current = 0
        self._failed = False
        self._done_all = False
        self.queue_draw()

    def set_step(self, idx: int):
        """Advance to step idx (never goes backwards)."""
        if idx > self._current:
            self._current = min(idx, len(self._steps) - 1)
        self.queue_draw()

    @property
    def step(self) -> int:
        return self._current

    def set_failed(self):
        self._failed = True
        self.queue_draw()

    def set_done(self):
        self._done_all = True
        self._current = len(self._steps) - 1
        self.queue_draw()

    def _on_draw(self, _w, cr):
        W = self.get_allocated_width()
        n = len(self._steps)
        if n == 0:
            return False
        fg = _fg_rgba(self)
        blue = theme.rgb(theme.BLUE)
        blue_l = theme.rgb(theme.BLUE_LIGHT)
        red = theme.rgb(theme.RED)
        pad = 56
        y = 14
        xs = [pad + (W - 2 * pad) * i / max(n - 1, 1) for i in range(n)]

        # connectors
        for i in range(n - 1):
            done = i < self._current or self._done_all
            cr.set_source_rgba(*(blue if done else fg), 0.9 if done else 0.15)
            cr.set_line_width(2.5)
            cr.move_to(xs[i] + 8, y)
            cr.line_to(xs[i + 1] - 8, y)
            cr.stroke()

        layout = PangoCairo.create_layout(cr)
        for i, x in enumerate(xs):
            done = i < self._current or self._done_all
            active = (i == self._current) and not self._done_all
            if self._failed and active:
                cr.set_source_rgba(*red, 1)
                cr.arc(x, y, 6, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgba(1, 1, 1, 1)
                cr.set_line_width(1.8)
                cr.move_to(x - 2.5, y - 2.5); cr.line_to(x + 2.5, y + 2.5)
                cr.move_to(x + 2.5, y - 2.5); cr.line_to(x - 2.5, y + 2.5)
                cr.stroke()
            elif done:
                cr.set_source_rgba(*blue, 1)
                cr.arc(x, y, 6, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgba(1, 1, 1, 1)
                cr.set_line_width(1.8)
                cr.move_to(x - 3, y)
                cr.line_to(x - 0.8, y + 2.4)
                cr.line_to(x + 3.2, y - 2.6)
                cr.stroke()
            elif active:
                pulse = 0.5 + 0.5 * math.sin(self._t * 4.0)
                cr.set_source_rgba(*blue_l, 0.25 * pulse + 0.05)
                cr.arc(x, y, 11 + 3 * pulse, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgba(*blue_l, 1)
                cr.arc(x, y, 6, 0, 2 * math.pi)
                cr.fill()
            else:
                cr.set_source_rgba(*fg, 0.25)
                cr.set_line_width(1.5)
                cr.arc(x, y, 5.5, 0, 2 * math.pi)
                cr.stroke()

            # label
            text = self._steps[i]
            layout.set_text(text, -1)
            font = Pango.FontDescription("Sans 9")
            if active:
                font.set_weight(Pango.Weight.BOLD)
            layout.set_font_description(font)
            _ink, logical = layout.get_pixel_extents()
            tw = logical.width
            if self._failed and active:
                cr.set_source_rgba(*red, 1)
            elif active:
                cr.set_source_rgba(*fg, 1)
            elif done:
                cr.set_source_rgba(*fg, 0.75)
            else:
                cr.set_source_rgba(*fg, 0.4)
            lx = min(max(x - tw / 2, 2), max(W - tw - 2, 2))
            cr.move_to(lx, y + 14)
            PangoCairo.show_layout(cr, layout)
        return False


# ── Traffic graph ──────────────────────────────────────────────────────────── #

class TrafficGraph(Gtk.DrawingArea):
    """Area chart of download / upload rates over the last N seconds."""

    def __init__(self, samples: int = 90, height: int = 120):
        super().__init__()
        self._n = samples
        self._rx = deque([0.0] * samples, maxlen=samples)
        self._tx = deque([0.0] * samples, maxlen=samples)
        self.set_size_request(-1, height)
        self.set_hexpand(True)
        self.connect("draw", self._on_draw)

    def push(self, rx_rate: float, tx_rate: float):
        self._rx.append(float(rx_rate))
        self._tx.append(float(tx_rate))
        self.queue_draw()

    def reset(self):
        self._rx = deque([0.0] * self._n, maxlen=self._n)
        self._tx = deque([0.0] * self._n, maxlen=self._n)
        self.queue_draw()

    def _on_draw(self, _w, cr):
        W = self.get_allocated_width()
        H = self.get_allocated_height()
        fg = _fg_rgba(self)
        blue = theme.rgb(theme.BLUE)
        blue_l = theme.rgb(theme.BLUE_LIGHT)
        pad_l, pad_r, pad_t, pad_b = 6, 62, 8, 6
        gw = W - pad_l - pad_r
        gh = H - pad_t - pad_b
        if gw <= 10 or gh <= 10:
            return False

        peak = max(max(self._rx), max(self._tx), 1.0)
        top = _nice_ceiling(peak)

        def X(i):
            return pad_l + gw * i / (self._n - 1)

        def Y(v):
            return pad_t + gh * (1.0 - min(v, top) / top)

        # grid + labels
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans 8"))
        for frac in (1.0, 0.5, 0.0):
            yy = Y(top * frac)
            cr.set_source_rgba(*fg, 0.10 if frac else 0.25)
            cr.set_line_width(1)
            cr.move_to(pad_l, yy + 0.5)
            cr.line_to(pad_l + gw, yy + 0.5)
            cr.stroke()
            if frac:
                layout.set_text(format_bytes(top * frac, True), -1)
                _ink, lg = layout.get_pixel_extents()
                cr.set_source_rgba(*fg, 0.5)
                cr.move_to(W - pad_r + 8, yy - lg.height / 2)
                PangoCairo.show_layout(cr, layout)

        def area(series, color, fill_alpha, line_w):
            import cairo
            pts = list(series)
            cr.new_path()
            cr.move_to(X(0), Y(0))
            for i, v in enumerate(pts):
                cr.line_to(X(i), Y(v))
            cr.line_to(X(len(pts) - 1), Y(0))
            cr.close_path()
            grad = cairo.LinearGradient(0, pad_t, 0, pad_t + gh)
            grad.add_color_stop_rgba(0, *color, fill_alpha)
            grad.add_color_stop_rgba(1, *color, 0.02)
            cr.set_source(grad)
            cr.fill()
            cr.new_path()
            for i, v in enumerate(pts):
                if i == 0:
                    cr.move_to(X(i), Y(v))
                else:
                    cr.line_to(X(i), Y(v))
            cr.set_source_rgba(*color, 0.95)
            cr.set_line_width(line_w)
            cr.set_line_join(1)
            cr.stroke()

        area(self._rx, blue, 0.38, 2.0)
        area(self._tx, blue_l, 0.22, 1.5)
        return False


# ── Verbose log ────────────────────────────────────────────────────────────── #

class LogView(Gtk.Box):
    """Monospace, colour-tagged verbose log with copy / clear buttons."""

    MAX_LINES = 3000

    def __init__(self, min_height: int = 170):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("log-frame")

        # Toolbar
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.get_style_context().add_class("log-toolbar")
        title = Gtk.Label(label=_("VERBOSE CONNECTION LOG"), xalign=0)
        bar.pack_start(title, True, True, 0)
        self._count_lbl = Gtk.Label(label="")
        bar.pack_start(self._count_lbl, False, False, 6)

        copy_btn = Gtk.Button()
        copy_btn.set_image(Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.MENU))
        copy_btn.set_tooltip_text(_("Copy log to clipboard"))
        copy_btn.connect("clicked", self._on_copy)
        bar.pack_end(copy_btn, False, False, 0)

        clear_btn = Gtk.Button()
        clear_btn.set_image(Gtk.Image.new_from_icon_name("edit-clear-all-symbolic", Gtk.IconSize.MENU))
        clear_btn.set_tooltip_text(_("Clear log"))
        clear_btn.connect("clicked", lambda *_: self.clear())
        bar.pack_end(clear_btn, False, False, 0)
        self.pack_start(bar, False, False, 0)

        # Text view
        self._tv = Gtk.TextView()
        self._tv.set_editable(False)
        self._tv.set_cursor_visible(False)
        self._tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._tv.set_left_margin(10)
        self._tv.set_right_margin(10)
        self._tv.set_top_margin(6)
        self._tv.set_bottom_margin(6)
        self._tv.set_pixels_below_lines(1)
        self._tv.get_style_context().add_class("log-view")
        self._buf = self._tv.get_buffer()
        self._end_mark = self._buf.create_mark("end", self._buf.get_end_iter(), False)

        def tag(name, **props):
            return self._buf.create_tag(name, **props)

        tag("time", foreground="#7FA6C4")
        tag("src_app", foreground=theme.BLUE_LIGHT, weight=Pango.Weight.BOLD)
        tag("src_NetworkMgr", foreground="#9EC5E6", weight=Pango.Weight.BOLD)
        tag("src_openvpn", foreground="#B9DCF5", weight=Pango.Weight.BOLD)
        tag("src_journal", foreground="#9EC5E6")
        tag("info", foreground="#CFE6F7")
        tag("ok", foreground="#7FE0B0")
        tag("warn", foreground="#FFC06A")
        tag("err", foreground="#FF7B7B", weight=Pango.Weight.BOLD)
        tag("step", foreground="#FFFFFF", weight=Pango.Weight.BOLD)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_min_content_height(min_height)
        self._scrolled.set_vexpand(True)
        self._scrolled.add(self._tv)
        self.pack_start(self._scrolled, True, True, 0)
        self._lines = 0

    # -- API ------------------------------------------------------------- #

    def append(self, source: str, message: str, level: str = "info",
               ts: Optional[str] = None) -> bool:
        ts = ts or time.strftime("%H:%M:%S")
        adj = self._scrolled.get_vadjustment()
        at_bottom = adj.get_value() + adj.get_page_size() >= adj.get_upper() - 40

        end = self._buf.get_end_iter()
        self._buf.insert_with_tags_by_name(end, f"{ts} ", "time")
        end = self._buf.get_end_iter()
        src_tag = f"src_{source}" if self._buf.get_tag_table().lookup(f"src_{source}") else "src_journal"
        self._buf.insert_with_tags_by_name(end, f"{source:<11}", src_tag)
        end = self._buf.get_end_iter()
        lvl_tag = level if self._buf.get_tag_table().lookup(level) else "info"
        self._buf.insert_with_tags_by_name(end, message + "\n", lvl_tag)
        self._lines += 1

        if self._lines > self.MAX_LINES:
            start = self._buf.get_start_iter()
            cut = self._buf.get_iter_at_line(self._lines - self.MAX_LINES)
            self._buf.delete(start, cut)
            self._lines = self.MAX_LINES
        self._count_lbl.set_text(str(self._lines))
        if at_bottom:
            GLib.idle_add(self._scroll_to_end)
        return False  # usable directly as a GLib.idle_add callback

    def _scroll_to_end(self):
        self._tv.scroll_mark_onscreen(self._end_mark)
        return False

    def clear(self):
        self._buf.set_text("")
        self._lines = 0
        self._count_lbl.set_text("")

    @property
    def line_count(self) -> int:
        return self._lines

    def get_text(self) -> str:
        return self._buf.get_text(self._buf.get_start_iter(), self._buf.get_end_iter(), False)

    def _on_copy(self, _btn):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(self.get_text(), -1)
