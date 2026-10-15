"""
Live monitoring helpers used by the connection view.

  JournalTail      — follows the system journal (NetworkManager + nm-openvpn)
                     and delivers parsed lines to the GTK main loop.
  VpnStatePoller   — polls NetworkManager's VPN state while connecting.
  TrafficSampler   — samples the tunnel interface byte counters every second.

All callbacks are invoked on the GTK main thread via GLib.idle_add.
"""
import re
import subprocess
import threading
import time
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib

from .vpn_manager import VPNManager

# "Oct 15 11:49:08.203909 host nm-openvpn[1068273]: message"
_JOURNAL_RE = re.compile(
    r"^(?P<mon>[A-Za-z]{3})\s+(?P<day>\d+)\s+(?P<time>\d\d:\d\d:\d\d)"
    r"(?:\.(?P<frac>\d+))?\s+(?P<host>\S+)\s+"
    r"(?P<src>[^\s\[:]+)(?:\[(?P<pid>\d+)\])?:\s?(?P<msg>.*)$"
)
# NetworkManager prefixes: "<info>  [1792057748.4302] message"
_NM_LEVEL_RE = re.compile(r"^<(?P<lvl>\w+)>\s+(?:\[[\d.]+\]\s*)?(?P<msg>.*)$")

_ERR_WORDS = re.compile(
    r"AUTH_FAILED|TLS Error|TLS handshake failed|Connection refused|"
    r"Cannot resolve|RESOLVE:|failed|fatal|error|timed out|Inactivity timeout|"
    r"Exiting due to|SIGUSR1|Options error",
    re.IGNORECASE,
)
_WARN_WORDS = re.compile(r"WARNING|deprecated|NOTE:|warn", re.IGNORECASE)


class JournalTail:
    """Follow NetworkManager / nm-openvpn journal lines in a background thread."""

    CMD = [
        "journalctl", "-f", "-n", "0", "-o", "short-precise", "--no-pager",
        "_SYSTEMD_UNIT=NetworkManager.service",
        "+", "SYSLOG_IDENTIFIER=nm-openvpn",
        "+", "_COMM=openvpn",
    ]

    def __init__(self, on_line: Callable[[str, str, str, str], None],
                 on_notice: Callable[[str, str], None]):
        """
        on_line(source, message, level, timestamp)  — a journal line
        on_notice(level, message)                   — tail status messages
        """
        self._on_line = on_line
        self._on_notice = on_notice
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pending_stop = None   # GLib source id of a delayed stop

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self._pending_stop is not None:
            # A delayed stop is scheduled: cancel it and keep the running tail.
            GLib.source_remove(self._pending_stop)
            self._pending_stop = None
        if self.running:
            return
        self._stop.clear()
        try:
            self._proc = subprocess.Popen(
                self.CMD,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            GLib.idle_add(self._on_notice, "warn",
                          "journalctl not found — system log unavailable")
            self._proc = None
            return
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        threading.Thread(target=self._stderr_reader, daemon=True).start()

    def stop(self, delay: float = 0.0) -> None:
        """Stop following; with delay, keep tailing a few more seconds first."""
        proc = self._proc
        if proc is None:
            return

        def _kill():
            self._pending_stop = None
            self._stop.set()
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            if self._proc is proc:
                self._proc = None
            return False

        if delay > 0:
            if self._pending_stop is None:
                self._pending_stop = GLib.timeout_add(int(delay * 1000), _kill)
        else:
            if self._pending_stop is not None:
                GLib.source_remove(self._pending_stop)
                self._pending_stop = None
            _kill()

    # -- threads -------------------------------------------------------- #

    def _reader(self):
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            if self._proc is not proc:
                break
            line = raw.rstrip("\n")
            if not line or line.startswith("-- "):
                continue
            parsed = self._parse(line)
            if parsed:
                GLib.idle_add(self._on_line, *parsed)

    def _stderr_reader(self):
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw in proc.stderr:
            text = raw.strip()
            if not text:
                continue
            if "not seeing messages" in text or "Permission denied" in text:
                GLib.idle_add(
                    self._on_notice, "warn",
                    "System journal not readable — add your user to the "
                    "'adm' or 'systemd-journal' group to see NetworkManager / "
                    "OpenVPN output here.",
                )
            elif "Hint:" in text or "Journal file" in text:
                continue
            else:
                GLib.idle_add(self._on_notice, "warn", f"journalctl: {text}")

    @staticmethod
    def _parse(line: str):
        m = _JOURNAL_RE.match(line)
        if not m:
            return ("journal", line, "info", time.strftime("%H:%M:%S"))
        src = m.group("src")
        msg = m.group("msg")
        frac = (m.group("frac") or "000")[:3]
        ts = f"{m.group('time')}.{frac}"
        level = "info"
        if src == "NetworkManager":
            nm = _NM_LEVEL_RE.match(msg)
            if nm:
                lvl = nm.group("lvl").lower()
                msg = nm.group("msg")
                if lvl.startswith("warn"):
                    level = "warn"
                elif lvl.startswith("err"):
                    level = "err"
            src = "NetworkMgr"
        elif src in ("nm-openvpn", "openvpn"):
            src = "openvpn"
            if _ERR_WORDS.search(msg):
                level = "err"
            elif _WARN_WORDS.search(msg):
                level = "warn"
        return (src, msg, level, ts)


class VpnStatePoller:
    """Poll NetworkManager's VPN state for a profile while it is connecting."""

    def __init__(self, vpn: VPNManager, profile: str,
                 on_state: Callable[[int, str], None], interval: float = 0.4):
        self._vpn = vpn
        self._profile = profile
        self._on_state = on_state
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self):
        last = None
        while not self._stop.is_set():
            info = self._vpn.get_active_info(self._profile)
            state = info["vpn_state"]
            if state != last and state >= 0:
                last = state
                GLib.idle_add(self._on_state, state, info["vpn_state_text"])
            if self._stop.wait(self._interval):
                break


class TrafficSampler:
    """Sample rx/tx byte counters of an interface once per second (main loop)."""

    def __init__(self, iface: str,
                 on_sample: Callable[[float, float, int, int], None]):
        """on_sample(rx_rate_Bps, tx_rate_Bps, rx_total, tx_total)"""
        self.iface = iface
        self._on_sample = on_sample
        self._source = None
        self._last = None  # (t, rx, tx)
        self.peak_rx = 0.0
        self.peak_tx = 0.0

    def start(self) -> None:
        if self._source is not None:
            return
        rx, tx = VPNManager.read_iface_counters(self.iface)
        self._last = (time.monotonic(), rx, tx)
        self._source = GLib.timeout_add(1000, self._tick)

    def stop(self) -> None:
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None

    @property
    def running(self) -> bool:
        return self._source is not None

    def _tick(self) -> bool:
        now = time.monotonic()
        rx, tx = VPNManager.read_iface_counters(self.iface)
        t0, rx0, tx0 = self._last
        dt = max(now - t0, 1e-3)
        rx_rate = max(0.0, (rx - rx0) / dt)
        tx_rate = max(0.0, (tx - tx0) / dt)
        self._last = (now, rx, tx)
        self.peak_rx = max(self.peak_rx, rx_rate)
        self.peak_tx = max(self.peak_tx, tx_rate)
        self._on_sample(rx_rate, tx_rate, rx, tx)
        return True
