#!/usr/bin/env python3
"""Benchmarks for monitor-ui and the CLI. Run under tests/run-headless.sh.

    perf-bench.py [--runs N] [--toggle CONNECTOR]

Prints one JSON object: median and p95 (ms) for GUI cold start to first frame, toggle round trip,
reload, and CLI `monitor list` wall time plus max RSS.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

import ui_harness as h

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402


def stats(samples):
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"median_ms": round(statistics.median(ordered), 2), "p95_ms": round(p95, 2), "n": len(ordered)}


def first_frame_child():
    """Child mode: launch the real app and print wall time of the first painted frame."""
    ui = h.load_ui()
    app = ui.App()

    def on_activate(app_):
        win = app_.props.active_window
        clock = win.get_frame_clock()

        def on_paint(*_):
            print(time.time(), flush=True)
            app_.quit()

        clock.connect("after-paint", on_paint)

    app.connect_after("activate", on_activate)
    app.run(None)


def bench_first_frame(runs):
    samples = []
    for _ in range(runs):
        start = time.time()
        out = subprocess.run(
            [sys.executable, __file__, "--first-frame-child"], capture_output=True, text=True, check=True
        )
        samples.append((float(out.stdout.split()[-1]) - start) * 1000)
    return stats(samples)


def bench_in_process(runs, connector):
    ui = h.load_ui()
    Adw.init()
    app = Adw.Application(application_id="io.github.anilsoylu.MonitorToggle.Bench")
    app.register(None)
    win = ui.Window(app)
    win.present()
    h.settle(win)

    reload_ms = []
    for _ in range(runs * 10):
        t = time.perf_counter()
        win.reload()
        h.settle(win)
        reload_ms.append((time.perf_counter() - t) * 1000)

    toggle_ms = []
    for _ in range(runs):
        for want in (False, True):
            t = time.perf_counter()
            h.row_for(win, connector).set_active(want)
            h.settle(win)
            toggle_ms.append((time.perf_counter() - t) * 1000)
            if h.row_for(win, connector).get_active() != want:
                raise RuntimeError(f"toggle {connector} -> {want} did not apply")
    win.destroy()
    return stats(reload_ms), stats(toggle_ms)


def bench_cli(runs):
    samples, rss = [], []
    cli = os.path.join(h.ROOT, "monitor")
    for _ in range(runs):
        t = time.perf_counter()
        proc = subprocess.Popen([sys.executable, cli, "list"], stdout=subprocess.DEVNULL)
        _pid, status, usage = os.wait4(proc.pid, 0)
        samples.append((time.perf_counter() - t) * 1000)
        if os.waitstatus_to_exitcode(status) != 0:
            raise RuntimeError("monitor list failed")
        rss.append(usage.ru_maxrss)
    return {**stats(samples), "max_rss_kb": max(rss)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--toggle", default="Meta-2")
    ap.add_argument("--first-frame-child", action="store_true")
    args = ap.parse_args()
    if args.first_frame_child:
        first_frame_child()
        return
    result = {"first_frame": bench_first_frame(args.runs), "cli_list": bench_cli(args.runs)}
    result["reload"], result["toggle"] = bench_in_process(args.runs, args.toggle)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
