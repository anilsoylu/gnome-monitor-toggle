#!/usr/bin/env python3
"""Render monitor-ui offscreen to PNG files. Run under tests/run-headless.sh.

    take-screenshots.py OUT_DIR

Writes all-on, one-off and error states in light and dark.
"""
import os
import sys
import time

import ui_harness as h

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import monitorctl  # noqa: E402


def save(win, path):
    h.settle(win)
    ctx = GLib.MainContext.default()
    end = time.monotonic() + 0.6  # let switch and page transitions finish
    while time.monotonic() < end:
        ctx.iteration(False)
        time.sleep(0.01)
    paintable = Gtk.WidgetPaintable.new(win)
    w, h_ = win.get_width(), win.get_height()
    node = None
    while node is None:  # a page switch can leave the paintable empty until the next frame
        h.settle(win)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, w, h_)
        node = snapshot.to_node()
    texture = win.get_native().get_renderer().render_texture(node, None)
    texture.save_to_png(path)
    print(path)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    ui = h.load_ui()
    Adw.init()
    app = Adw.Application(application_id="io.github.anilsoylu.MonitorToggle.Shots")
    app.register(None)
    style = Adw.StyleManager.get_default()
    for scheme, tag in ((Adw.ColorScheme.FORCE_LIGHT, "light"), (Adw.ColorScheme.FORCE_DARK, "dark")):
        style.set_color_scheme(scheme)
        monitorctl.run("all")
        win = ui.Window(app)
        win.present()
        save(win, f"{out}/{tag}-all-on.png")
        monitorctl.run("off", "Meta-1")
        save(win, f"{out}/{tag}-one-off.png")
        win._show_error(monitorctl._("GNOME display settings are not available in this session."))
        save(win, f"{out}/{tag}-error.png")
        win.close()
    monitorctl.run("all")


if __name__ == "__main__":
    main()
