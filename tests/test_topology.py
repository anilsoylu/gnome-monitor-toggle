"""Unit tests for the pure layout functions in monitorctl (no D-Bus needed)."""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import monitorctl  # noqa: E402


def mode(mode_id, width, height, rate, current=False, preferred=False):
    props = {}
    if current:
        props["is-current"] = True
    if preferred:
        props["is-preferred"] = True
    return (mode_id, width, height, rate, 1.0, [1.0], props)


def monitor(conn, *modes):
    return ((conn, "VEN", "Model", "0"), list(modes), {"display-name": f"Display {conn}"})


def logical(x, y, primary, conn, scale=1.0, transform=0):
    return (x, y, scale, transform, primary, [(conn, "VEN", "Model", "0")], {})


# DP-1: 240 Hz panel, DP-2: 144 Hz, HDMI-1: 1280x1024. Only modes that matter for the tests.
DP1 = monitor(
    "DP-1",
    mode("1920x1080@60.000", 1920, 1080, 60.0),
    mode("1920x1080@239.757", 1920, 1080, 239.757, preferred=True),
    mode("1920x1080@239.757+vrr", 1920, 1080, 239.9),
)
DP2 = monitor("DP-2", mode("1920x1080@144.001", 1920, 1080, 144.001, preferred=True))
HDMI = monitor("HDMI-1", mode("1280x1024@60.020", 1280, 1024, 60.02, preferred=True))


def with_current(mon):
    """Same monitor with its preferred mode marked as current (= the display is on)."""
    (ident, modes, props) = mon
    marked = [m[:6] + ({**m[6], "is-current": True},) if m[6].get("is-preferred") else m for m in modes]
    return (ident, marked, props)


ALL_ON = [with_current(DP1), with_current(DP2), with_current(HDMI)]
ROW = [logical(0, 0, True, "DP-1"), logical(1920, 0, False, "DP-2"), logical(3840, 0, False, "HDMI-1")]


def positions(layout):
    return [(lm[5][0][0], lm[0], lm[1], lm[4]) for lm in layout]


class CurrentModeTest(unittest.TestCase):
    def test_enabled_display_keeps_its_active_mode(self):
        self.assertEqual(monitorctl.current_mode(ALL_ON, "DP-1")[0], "1920x1080@239.757")

    def test_disabled_display_gets_highest_non_vrr_rate_at_preferred_size(self):
        self.assertEqual(monitorctl.current_mode([DP1], "DP-1")[0], "1920x1080@239.757")

    def test_unknown_connector(self):
        self.assertIsNone(monitorctl.current_mode([DP1], "DP-9"))


class PackTest(unittest.TestCase):
    def plan(self, monitors, logicals, action, connector=None, baseline=None):
        state = (7, monitors, logicals, {})
        settings = {"baseline": baseline or {}, "persist": False}
        return monitorctl.plan(state, settings, action, connector)

    def test_turn_off_middle_closes_the_gap(self):
        _serial, layout, _settings = self.plan(ALL_ON, ROW, "off", "DP-2")
        self.assertEqual(positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 1920, 0, False)])

    def test_turn_off_primary_moves_primary_to_the_leftmost(self):
        _serial, layout, _settings = self.plan(ALL_ON, ROW, "off", "DP-1")
        self.assertEqual(positions(layout), [("DP-2", 0, 0, True), ("HDMI-1", 1920, 0, False)])

    def test_only_keeps_one_display_at_origin_as_primary(self):
        _serial, layout, _settings = self.plan(ALL_ON, ROW, "only", "HDMI-1")
        self.assertEqual(positions(layout), [("HDMI-1", 0, 0, True)])

    def test_vertical_stack_closes_the_gap(self):
        stack = [logical(0, 0, True, "DP-1"), logical(0, 1080, False, "DP-2"), logical(0, 2160, False, "HDMI-1")]
        _serial, layout, _settings = self.plan(ALL_ON, stack, "off", "DP-2")
        self.assertEqual(positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 0, 1080, False)])

    def test_scaled_display_uses_logical_width(self):
        scaled = [logical(0, 0, True, "DP-1", scale=2.0), logical(960, 0, False, "DP-2"), logical(2880, 0, False, "HDMI-1")]
        _serial, layout, _settings = self.plan(ALL_ON, scaled, "off", "DP-2")
        self.assertEqual(positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 960, 0, False)])

    def test_rotated_display_swaps_width_and_height(self):
        rotated = [logical(0, 0, True, "DP-1", transform=1), logical(1080, 0, False, "DP-2"), logical(3000, 0, False, "HDMI-1")]
        _serial, layout, _settings = self.plan(ALL_ON, rotated, "off", "DP-2")
        self.assertEqual(positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 1080, 0, False)])

    def test_set_restores_an_explicit_selection(self):
        _serial, layout, _settings = self.plan(ALL_ON, ROW[:1], "set", ["DP-1", "HDMI-1"])
        self.assertEqual(positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 1920, 0, False)])

    def test_last_display_cannot_be_turned_off(self):
        with self.assertRaises(monitorctl.DisplayError):
            self.plan([with_current(DP1)], [logical(0, 0, True, "DP-1")], "off", "DP-1")

    def test_unknown_connector_is_rejected(self):
        with self.assertRaises(monitorctl.DisplayError):
            self.plan(ALL_ON, ROW, "off", "DP-9")

    def test_turn_on_restores_saved_position_and_mode(self):
        partly = [DP1, with_current(DP2), with_current(HDMI)]
        live = [logical(0, 0, True, "DP-2"), logical(1920, 0, False, "HDMI-1")]
        _serial, _layout, settings = self.plan(ALL_ON, ROW, "off", "DP-1")
        _serial, layout, _settings = self.plan(partly, live, "on", "DP-1", baseline=settings["baseline"])
        self.assertEqual(
            positions(layout), [("DP-1", 0, 0, True), ("DP-2", 1920, 0, False), ("HDMI-1", 3840, 0, False)]
        )
        self.assertEqual(layout[0][5][0][1], "1920x1080@239.757")

    def test_display_missing_from_saved_layout_goes_right_and_one_primary_wins(self):
        partly = [DP1, with_current(DP2), with_current(HDMI)]
        live = [logical(0, 0, True, "DP-2"), logical(1920, 0, False, "HDMI-1")]
        baseline = {"DP-1": [0, 0, 1.0, 0, True, [("DP-1", "1920x1080@239.757", {})]]}
        _serial, layout, _settings = self.plan(partly, live, "on", "DP-1", baseline=baseline)
        self.assertEqual(
            positions(layout), [("DP-1", 0, 0, True), ("DP-2", 1920, 0, False), ("HDMI-1", 3840, 0, False)]
        )

    def test_without_saved_layout_live_positions_are_kept(self):
        partly = [with_current(DP1), with_current(DP2), HDMI]
        stack = [logical(0, 0, True, "DP-1"), logical(0, 1080, False, "DP-2")]
        _serial, layout, _settings = self.plan(partly, stack, "on", "HDMI-1")
        self.assertEqual(
            positions(layout), [("DP-1", 0, 0, True), ("HDMI-1", 1920, 0, False), ("DP-2", 0, 1080, False)]
        )

    def test_all_on_layout_becomes_the_new_baseline(self):
        _serial, _layout, settings = self.plan(ALL_ON, ROW, "off", "HDMI-1")
        self.assertEqual(settings["baseline"]["HDMI-1"][:5], [3840, 0, 1.0, 0, False])


class SettingsFileTest(unittest.TestCase):
    def test_round_trip_keeps_baseline_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "state.json")
            settings = {"baseline": {"DP-1": [0, 0, 1.0, 0, True, [["DP-1", "m", {}]]]}, "persist": True}
            monitorctl.save_settings(settings, path)
            self.assertEqual(
                monitorctl.load_settings(path),
                {"baseline": {"DP-1": [0, 0, 1.0, 0, True, [("DP-1", "m", {})]]}, "persist": True},
            )
            self.assertEqual(os.listdir(os.path.dirname(path)), ["state.json"])

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as fh:
                fh.write("{not json")
            original, monitorctl.LEGACY_STATE_FILE = monitorctl.LEGACY_STATE_FILE, os.path.join(tmp, "none.json")
            try:
                self.assertEqual(monitorctl.load_settings(path), {"baseline": {}, "persist": False})
            finally:
                monitorctl.LEGACY_STATE_FILE = original

    def test_wrong_shape_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as fh:
                json.dump({"baseline": {"DP-1": [0, 0]}}, fh)
            original, monitorctl.LEGACY_STATE_FILE = monitorctl.LEGACY_STATE_FILE, os.path.join(tmp, "none.json")
            try:
                self.assertEqual(monitorctl.load_settings(path), {"baseline": {}, "persist": False})
            finally:
                monitorctl.LEGACY_STATE_FILE = original

    def test_legacy_cache_file_is_read_when_no_state_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = os.path.join(tmp, "monitor-toggle.json")
            with open(legacy, "w") as fh:
                json.dump({"baseline": {"DP-2": [1920, 0, 1.0, 0, False, [["DP-2", "m", {}]]]}}, fh)
            original, monitorctl.LEGACY_STATE_FILE = monitorctl.LEGACY_STATE_FILE, legacy
            try:
                loaded = monitorctl.load_settings(os.path.join(tmp, "missing.json"))
            finally:
                monitorctl.LEGACY_STATE_FILE = original
            self.assertEqual(loaded["baseline"]["DP-2"][0], 1920)
            self.assertFalse(loaded["persist"])


if __name__ == "__main__":
    unittest.main()
