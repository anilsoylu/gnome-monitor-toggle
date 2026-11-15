"""Helpers shared by the benchmark and leak-check scripts.

They drive the real `monitor-ui` window against a headless Mutter, so they must run under
tests/run-headless.sh. The helpers only rely on `Window.reload()`, `Window._busy` and `Window._rows`.
"""
import importlib.machinery
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gi.repository import GLib  # noqa: E402


def load_ui():
    """Import the extensionless `monitor-ui` script as a module."""
    loader = importlib.machinery.SourceFileLoader("monitor_ui", str(ROOT / "monitor-ui"))
    spec = importlib.util.spec_from_loader("monitor_ui", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def rows(win):
    found = win._rows
    return dict(found) if isinstance(found, dict) else {r.get_title(): r for r in found}


def row_for(win, connector):
    for key, row in rows(win).items():
        if key == connector or connector in (row.get_title(), row.get_subtitle() or ""):
            return row
    raise KeyError(connector)


def settle(win, timeout=10.0):
    """Run the main loop until the window is idle (no busy apply, no pending events)."""
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(timeout * 1e6)
    while GLib.get_monotonic_time() < deadline:
        while ctx.iteration(False):
            pass
        if not getattr(win, "_busy", False) and not getattr(win, "_pending", False):
            return
        ctx.iteration(True)
    raise TimeoutError("window did not settle")


def rss_kb():
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0
