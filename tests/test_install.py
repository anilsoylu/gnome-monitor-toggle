"""install.sh / uninstall.sh into a throwaway HOME."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_ID = "io.github.anilsoylu.MonitorToggle"


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"]}

    def tearDown(self):
        shutil.rmtree(self.home)

    def sh(self, script):
        return subprocess.run(["bash", str(ROOT / script)], env=self.env, capture_output=True, text=True)

    def test_install_then_uninstall(self):
        result = self.sh("install.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = [
            ".local/bin/monitor",
            ".local/bin/monitor-ui",
            ".local/bin/monitorctl.py",
            f".local/share/applications/{APP_ID}.desktop",
            ".local/share/locale/tr/LC_MESSAGES/monitor-toggle.mo",
        ]
        for rel in installed:
            self.assertTrue((self.home / rel).is_file(), rel)
        desktop = (self.home / f".local/share/applications/{APP_ID}.desktop").read_text()
        self.assertIn(f"Exec={self.home}/.local/bin/monitor-ui", desktop)

        result = self.sh("uninstall.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel in installed:
            self.assertFalse((self.home / rel).exists(), rel)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-utils not installed")
    def test_desktop_file_is_valid(self):
        self.assertEqual(self.sh("install.sh").returncode, 0)
        result = subprocess.run(
            ["desktop-file-validate", str(self.home / f".local/share/applications/{APP_ID}.desktop")],
            capture_output=True, text=True,
        )
        self.assertEqual(result.stdout + result.stderr, "")


if __name__ == "__main__":
    unittest.main()
