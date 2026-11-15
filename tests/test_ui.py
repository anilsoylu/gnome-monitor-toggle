"""monitor-ui against a headless Mutter: the window must not overwrite what the CLI saved meanwhile.

Run under tests/run-headless.sh (three virtual monitors).
"""
import json
import os
import subprocess
import sys
import unittest

from test_integration import ROOT, STATE_FILES, layout, reset_layout

import ui_harness as h


def cli(*args):
    subprocess.run([sys.executable, str(ROOT / "monitor"), *args], check=True, capture_output=True)


@unittest.skipUnless(os.environ.get("GMT_IN_SESSION") == "1", "needs tests/run-headless.sh")
class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gi.repository import Adw

        Adw.init()
        cls.ui = h.load_ui()
        cls.app = Adw.Application(application_id="io.github.anilsoylu.MonitorToggle.Test")
        cls.app.register(None)

    def setUp(self):
        for path in STATE_FILES:
            path.unlink(missing_ok=True)
        reset_layout(["Meta-2", "Meta-0", "Meta-1"])
        self.win = self.ui.Window(self.app)  # opened with no saved layout
        self.win.present()
        h.settle(self.win)

    def tearDown(self):
        self.win.close()
        h.settle(self.win)

    def test_turning_on_uses_layout_saved_by_cli_after_launch(self):
        cli("off", "Meta-0")
        h.settle(self.win)
        h.row_for(self.win, "Meta-0").set_active(True)
        h.settle(self.win)
        self.assertEqual(
            layout(), {"Meta-2": (0, 0, True), "Meta-0": (1280, 0, False), "Meta-1": (3200, 0, False)}
        )

    def test_persist_switch_keeps_layout_saved_by_cli(self):
        cli("off", "Meta-0")
        h.settle(self.win)
        self.win.persist_row.set_active(True)
        saved = json.loads(STATE_FILES[0].read_text())
        self.assertTrue(saved["persist"])
        self.assertEqual(saved["baseline"]["Meta-0"][:2], [1280, 0])


if __name__ == "__main__":
    unittest.main()
