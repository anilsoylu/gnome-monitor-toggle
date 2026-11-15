"""Checks for po/*.po: valid syntax, matching placeholders, and a loadable compiled catalog."""
import gettext
import importlib.util
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

PO_DIR = pathlib.Path(__file__).resolve().parent.parent / "po"
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")

spec = importlib.util.spec_from_file_location("compile_translations", PO_DIR / "compile-translations.py")
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)

LANGS = (PO_DIR / "LINGUAS").read_text().split()


class TranslationTest(unittest.TestCase):
    def test_placeholders_match(self):
        for lang in LANGS:
            for msgid, msgstr in compiler.parse_po(PO_DIR / f"{lang}.po").items():
                if msgid:
                    self.assertEqual(
                        sorted(PLACEHOLDER.findall(msgid)), sorted(PLACEHOLDER.findall(msgstr)), f"{lang}: {msgid}"
                    )

    def test_every_template_string_is_translated(self):
        template = set(compiler.parse_po_template(PO_DIR / "monitor-toggle.pot"))
        for lang in LANGS:
            self.assertEqual(template - set(compiler.parse_po(PO_DIR / f"{lang}.po")), set(), lang)

    def test_compiled_catalog_loads_with_gettext(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["python3", str(PO_DIR / "compile-translations.py"), tmp], check=True, capture_output=True
            )
            tr = gettext.translation("monitor-toggle", tmp, languages=["tr"])
            self.assertEqual(tr.gettext("Turn All On"), "Hepsini Aç")
            self.assertEqual(tr.gettext("{name} turned off").format(name="DP-1"), "DP-1 kapatıldı")

    @unittest.skipUnless(shutil.which("msgfmt"), "gettext msgfmt not installed")
    def test_msgfmt_check_passes(self):
        for lang in LANGS:
            result = subprocess.run(
                ["msgfmt", "--check", "-o", "/dev/null", str(PO_DIR / f"{lang}.po")], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
