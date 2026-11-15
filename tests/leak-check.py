#!/usr/bin/env python3
"""Memory-leak check for monitor-ui. Run under tests/run-headless.sh.

    leak-check.py [--reloads N] [--toggles N] [--toggle CONNECTOR]

Drives the real window: N reloads, then N off/on toggles of one display. Samples VmRSS and Python object
counts, and prints the RSS slope after warm-up plus the object types that grew the most.

Headless Mutter 50.1 itself grows by tens of MB per ApplyMonitorsConfig (server side, measured with the CLI
alone), so keep toggles low and virtual monitors small:
    VIRTUAL_MONITORS="640x480@60 640x480@60 640x480@60" tests/run-in-docker.sh python3 tests/leak-check.py
Mutter's RSS is reported separately and is not part of the pass/fail verdict for this app.
"""
import argparse
import collections
import gc
import json
import subprocess
import tracemalloc

import ui_harness as h

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

WARMUP = 20
SAMPLE_EVERY = 10
MAX_SLOPE_KB = 1.0


def type_counts():
    gc.collect()
    return collections.Counter(type(o).__name__ for o in gc.get_objects())


def mutter_rss_kb():
    out = subprocess.run(["ps", "-o", "rss=", "-C", "mutter"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else 0


def slope(points):
    """Least-squares slope (KB per iteration) of (iteration, rss_kb) points."""
    n = len(points)
    if n < 2:
        return 0.0
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    num = sum((x - mx) * (y - my) for x, y in points)
    den = sum((x - mx) ** 2 for x, _ in points) or 1
    return num / den


def run_phase(win, iterations, step):
    points = []
    for i in range(WARMUP):
        step(i)
    gc.collect()
    before_types = type_counts()
    snap_before = tracemalloc.take_snapshot()
    mutter_before = mutter_rss_kb()
    for i in range(iterations):
        step(i)
        if i % SAMPLE_EVERY == 0:
            gc.collect()
            points.append((i, h.rss_kb()))
    growth = type_counts() - before_types
    top_alloc = [
        f"{s.traceback[0].filename.rsplit('/', 1)[-1]}:{s.traceback[0].lineno} +{s.size_diff // 1024} KB"
        for s in tracemalloc.take_snapshot().compare_to(snap_before, "lineno")[:5]
    ]
    return {
        "iterations": iterations,
        "rss_start_kb": points[0][1],
        "rss_end_kb": points[-1][1],
        "rss_slope_kb_per_iter": round(slope(points), 3),
        "pass": slope(points) < MAX_SLOPE_KB,
        "mutter_rss_growth_kb": mutter_rss_kb() - mutter_before,
        "py_objects_grown": dict(growth.most_common(5)),
        "top_tracemalloc": top_alloc,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reloads", type=int, default=5000)
    ap.add_argument("--toggles", type=int, default=60)
    ap.add_argument("--toggle", default="Meta-2")
    args = ap.parse_args()

    ui = h.load_ui()
    Adw.init()
    app = Adw.Application(application_id="io.github.anilsoylu.MonitorToggle.LeakCheck")
    app.register(None)
    win = ui.Window(app)
    win.present()
    h.settle(win)
    tracemalloc.start()

    def reload_step(_i):
        win.reload()
        h.settle(win)

    def toggle_step(i):
        h.row_for(win, args.toggle).set_active(i % 2 == 1)
        h.settle(win)

    report = {
        "reload": run_phase(win, args.reloads, reload_step),
        "toggle": run_phase(win, args.toggles, toggle_step),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
