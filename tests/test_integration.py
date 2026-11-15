"""End-to-end tests of the `monitor` CLI against a headless Mutter.

Run under tests/run-headless.sh with three virtual monitors (the default), e.g.
    tests/run-in-docker.sh python3 -m unittest discover -s tests -v
"""
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitorctl  # noqa: E402
from gi.repository import Gio, GLib  # noqa: E402

HOME = pathlib.Path.home()
STATE_FILES = [
    pathlib.Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "monitor-toggle/state.json",
    HOME / ".cache/monitor-toggle.json",
]


def cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "monitor"), *args], capture_output=True, text=True
    )


def reset_layout():
    """Apply Meta-0 | Meta-1 | Meta-2 side by side, Meta-0 primary, straight over D-Bus."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    args = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig")
    serial, monitors, _logicals, _props = bus.call_sync(
        *args, "GetCurrentState", None, None, Gio.DBusCallFlags.NONE, -1, None
    ).unpack()
    x, logicals = 0, []
    for ident, modes, _p in monitors:
        mode = next(m for m in modes if m[6].get("is-preferred"))
        logicals.append((x, 0, 1.0, 0, not logicals, [(ident[0], mode[0], {})]))
        x += mode[1]
    params = GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, logicals, {}))
    bus.call_sync(*args, "ApplyMonitorsConfig", params, None, Gio.DBusCallFlags.NONE, -1, None)


def layout():
    """{connector: (x, y, primary)} of the enabled displays."""
    _serial, _monitors, logicals, _props = monitorctl.get_state()
    return {mons[0][0]: (x, y, primary) for x, y, _s, _t, primary, mons, _p in logicals}


@unittest.skipUnless(os.environ.get("GMT_IN_SESSION") == "1", "needs tests/run-headless.sh")
class CliTest(unittest.TestCase):
    def setUp(self):
        for path in STATE_FILES:
            path.unlink(missing_ok=True)
        reset_layout()
        self.assertEqual(
            layout(), {"Meta-0": (0, 0, True), "Meta-1": (1920, 0, False), "Meta-2": (3840, 0, False)}
        )

    def test_turn_off_last_display(self):
        self.assertEqual(cli("off", "Meta-2").returncode, 0)
        self.assertEqual(layout(), {"Meta-0": (0, 0, True), "Meta-1": (1920, 0, False)})

    def test_turn_off_middle_display_closes_the_gap(self):
        result = cli("off", "Meta-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(layout(), {"Meta-0": (0, 0, True), "Meta-2": (1920, 0, False)})

    def test_turn_off_primary_moves_primary(self):
        self.assertEqual(cli("off", "Meta-0").returncode, 0)
        self.assertEqual(layout(), {"Meta-1": (0, 0, True), "Meta-2": (1920, 0, False)})

    def test_turn_back_on_restores_position(self):
        self.assertEqual(cli("off", "Meta-0").returncode, 0)
        self.assertEqual(cli("on", "Meta-0").returncode, 0)
        self.assertEqual(
            layout(), {"Meta-0": (0, 0, True), "Meta-1": (1920, 0, False), "Meta-2": (3840, 0, False)}
        )

    def test_last_enabled_display_cannot_be_turned_off(self):
        self.assertEqual(cli("off", "Meta-1").returncode, 0)
        self.assertEqual(cli("off", "Meta-2").returncode, 0)
        result = cli("off", "Meta-0")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(layout(), {"Meta-0": (0, 0, True)})

    def test_unknown_connector_fails(self):
        result = cli("off", "HDMI-9")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(layout()), 3)

    def test_single_primary_when_saved_layout_misses_a_display(self):
        # Meta-0 is saved as primary and turned off; Meta-1 becomes the live primary; the saved layout
        # does not know Meta-1/Meta-2 (as if they were plugged in later). Turning Meta-0 back on must not
        # send two primaries.
        self.assertEqual(cli("off", "Meta-0").returncode, 0)
        state_file = next(p for p in STATE_FILES if p.exists())
        data = json.loads(state_file.read_text())
        data["baseline"] = {"Meta-0": data["baseline"]["Meta-0"]}
        state_file.write_text(json.dumps(data))

        result = cli("on", "Meta-0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([conn for conn, (_x, _y, p) in layout().items() if p], ["Meta-0"])


if __name__ == "__main__":
    unittest.main()
