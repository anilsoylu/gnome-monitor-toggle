"""Shared core for turning GNOME displays on and off.

xrandr cannot disable outputs on Wayland, so this talks to Mutter's own D-Bus API
(org.gnome.Mutter.DisplayConfig). Both the `monitor` CLI and the `monitor-ui` GTK app use it.

Layout rules enforced by Mutter (meta-monitor-config-utils.c): exactly one primary logical
monitor, positions start at 0,0, monitors must not overlap and must be adjacent.
"""
import gettext
import json
import os

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.gnome.Mutter.DisplayConfig"
OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"
INTERFACE = "org.gnome.Mutter.DisplayConfig"
CALL_TIMEOUT_MS = 10_000

TEMPORARY = 1
PERSISTENT = 2

APPLY_SIGNATURE = "(uua(iiduba(ssa{sv}))a{sv})"
GETTEXT_DOMAIN = "monitor-toggle"
LEGACY_STATE_FILE = os.path.expanduser("~/.cache/monitor-toggle.json")


def _locale_dir():
    here = os.path.dirname(os.path.realpath(__file__))
    for candidate in (os.path.join(here, "build", "locale"), os.path.join(GLib.get_user_data_dir(), "locale")):
        if os.path.isdir(candidate):
            return candidate
    return None


_ = gettext.translation(GETTEXT_DOMAIN, _locale_dir(), fallback=True).gettext


class DisplayError(Exception):
    """An error with a message that is safe to show to the user."""


# ------------------------------------------------------------------ D-Bus ----
def bus():
    """The shared session bus connection (GLib returns the same object every time)."""
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def friendly_error(error):
    """Turn a GLib.Error from Mutter into a short message for the user."""
    if not isinstance(error, GLib.Error):
        return str(error)
    remote = Gio.DBusError.get_remote_error(error) or ""
    if remote.endswith(("ServiceUnknown", "NameHasNoOwner")):
        return _("GNOME display settings are not available in this session.")
    if remote.endswith("AccessDenied"):
        return _("The display setup changed in the meantime. Try again.")
    if remote.endswith("InvalidArgs"):
        Gio.DBusError.strip_remote_error(error)
        return _("GNOME rejected this layout: {reason}").format(reason=error.message)
    return error.message


def get_state(connection=None):
    """(serial, monitors, logical_monitors, properties) from GetCurrentState."""
    try:
        reply = (connection or bus()).call_sync(
            BUS_NAME, OBJECT_PATH, INTERFACE, "GetCurrentState",
            None, None, Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None,
        )
    except GLib.Error as exc:
        raise DisplayError(friendly_error(exc)) from exc
    return reply.unpack()


def apply_params(serial, layout, persist=False):
    """GLib.Variant arguments for ApplyMonitorsConfig."""
    method = PERSISTENT if persist else TEMPORARY
    return GLib.Variant(APPLY_SIGNATURE, (serial, method, [tuple(lm) for lm in layout], {}))


def apply(serial, layout, persist=False, connection=None):
    try:
        (connection or bus()).call_sync(
            BUS_NAME, OBJECT_PATH, INTERFACE, "ApplyMonitorsConfig",
            apply_params(serial, layout, persist), None, Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None,
        )
    except GLib.Error as exc:
        raise DisplayError(friendly_error(exc)) from exc


# ----------------------------------------------------------------- monitors ----
def connectors(monitors):
    return [ident[0] for ident, _modes, _props in monitors]


def enabled_map(logicals):
    """{connector: (x, y, primary)} for the displays that are currently on."""
    return {mon[0]: (x, y, primary) for x, y, _scale, _tr, primary, mons, _props in logicals for mon in mons}


def display_name(monitors, connector):
    for ident, _modes, props in monitors:
        if ident[0] == connector:
            return props.get("display-name") or f"{ident[1]} {ident[2]}"
    return connector


def current_mode(monitors, connector):
    """The mode to use for a display.

    An enabled display keeps its active mode. A disabled one gets the preferred resolution at its
    highest non-VRR refresh rate, so a 240 Hz panel does not come back at 60 Hz.
    """
    for ident, modes, _props in monitors:
        if ident[0] != connector:
            continue
        current = next((m for m in modes if m[6].get("is-current")), None)
        if current is not None or not modes:
            return current
        base = next((m for m in modes if m[6].get("is-preferred")), modes[0])
        same = [m for m in modes if (m[1], m[2]) == (base[1], base[2]) and "+vrr" not in m[0]]
        return max(same, key=lambda m: m[3]) if same else base
    return None


def _mode_id(monitors, connector):
    mode = current_mode(monitors, connector)
    return mode[0] if mode else None


def _logical_size(monitors, lm):
    """(width, height) of a logical monitor entry in layout coordinates."""
    mode = current_mode(monitors, lm[5][0][0])
    width, height = (mode[1], mode[2]) if mode else (1920, 1080)
    if lm[3] % 2:  # 90/270 degree transforms swap the axes
        width, height = height, width
    scale = lm[2] or 1
    return int(width / scale), int(height / scale)


# ------------------------------------------------------- layout (topology) ----
def _entry(x, y, scale, transform, primary, connector, mode_id):
    return [x, y, scale, transform, primary, [(connector, mode_id, {})]]


def _copy_entry(lm):
    """A mutable copy of a logical monitor entry."""
    mons = [(m[0], m[1], m[2] if len(m) > 2 else {}) for m in lm[5]]
    return [lm[0], lm[1], lm[2], lm[3], lm[4], mons]


def full_topology(monitors, logicals, baseline=None):
    """Layout of every connected display, on or off: {connector: entry}.

    With every display on, the live layout is the answer (and becomes the new baseline). Otherwise
    saved positions are used so displays come back where they were; a display that is neither saved
    nor on goes to the right of everything else. Modes always come from the live state.
    """
    baseline = baseline or {}
    known = connectors(monitors)
    live = {
        mon[0]: _entry(x, y, scale, tr, primary, mon[0], _mode_id(monitors, mon[0]))
        for x, y, scale, tr, primary, mons, _props in logicals
        for mon in mons
    }
    if set(known) <= set(live):
        return {conn: live[conn] for conn in known}

    saved = {conn: _copy_entry(baseline[conn]) for conn in known if conn in baseline}
    topo = dict(saved)
    right = max((lm[0] + _logical_size(monitors, lm)[0] for lm in saved.values()), default=0)
    for conn in known:
        if conn in topo:
            continue
        lm = live.get(conn) or _entry(0, 0, 1.0, 0, False, conn, _mode_id(monitors, conn))
        lm[0], lm[1] = right, 0
        right += _logical_size(monitors, lm)[0]
        topo[conn] = lm
    for conn in known:
        topo[conn][5] = [(conn, _mode_id(monitors, conn), {})]
    return topo


def _close_gaps(entries, axis, sizes):
    """Shift entries so the union of their spans on `axis` starts at 0 and has no holes."""
    spans = sorted((lm[axis], lm[axis] + size[axis]) for lm, size in zip(entries, sizes))
    shifts, removed, reach = [], spans[0][0], spans[0][0]
    shifts.append((spans[0][0], removed))
    for start, end in spans:
        if start > reach:
            removed += start - reach
            shifts.append((start, removed))
        reach = max(reach, end)
    for lm in entries:
        lm[axis] -= max(s for at, s in shifts if at <= lm[axis])


def pack(topo, enabled, monitors):
    """The ApplyMonitorsConfig layout for the displays in `enabled`.

    Removes the holes left by disabled displays and keeps exactly one primary: the first primary in
    reading order, or the top-left display when none is marked.
    """
    if not enabled:
        raise DisplayError(_("At least one display must stay on."))
    entries = sorted((_copy_entry(topo[c]) for c in enabled), key=lambda lm: (lm[1], lm[0]))
    sizes = [_logical_size(monitors, lm) for lm in entries]
    for axis in (0, 1):
        _close_gaps(entries, axis, sizes)
    primary = next((lm for lm in entries if lm[4]), entries[0])
    for lm in entries:
        lm[4] = lm is primary
    return entries


# --------------------------------------------------------------- state file ----
def state_path():
    return os.path.join(GLib.get_user_state_dir(), "monitor-toggle", "state.json")


def load_settings(path=None):
    """{"baseline": {connector: entry}, "persist": bool}; falls back to the pre-1.0 cache file."""
    for candidate in (path or state_path(), LEGACY_STATE_FILE):
        try:
            with open(candidate) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        try:
            return {
                "baseline": {str(k): _copy_entry(v) for k, v in data["baseline"].items()},
                "persist": bool(data.get("persist", False)),
            }
        except (AttributeError, IndexError, KeyError, TypeError):
            continue  # valid JSON with the wrong shape: ignore it like a missing file
    return {"baseline": {}, "persist": False}


def save_settings(settings, path=None):
    """Write atomically, so a crash never leaves a half-written layout behind."""
    path = path or state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        json.dump(settings, fh)
    os.replace(tmp, path)


# ------------------------------------------------------------------ actions ----
def plan(state, settings, action, connector=None):
    """Compute (serial, layout, new_settings) for an action without touching D-Bus.

    action: "on" | "off" | "only" | "all".
    """
    serial, monitors, logicals, _props = state
    known = connectors(monitors)
    if connector is not None and connector not in known:
        raise DisplayError(_("'{connector}' is not connected.").format(connector=connector))

    topo = full_topology(monitors, logicals, settings["baseline"])
    enabled = set(enabled_map(logicals))
    if action == "on":
        enabled.add(connector)
    elif action == "off":
        enabled.discard(connector)
    elif action == "only":
        enabled = {connector}
    elif action == "all":
        enabled = set(known)
    else:
        raise ValueError(action)
    return serial, pack(topo, enabled, monitors), {**settings, "baseline": topo}


def run(action, connector=None, persist=False, connection=None):
    """Read the live state, apply the action and save the layout (CLI entry point)."""
    connection = connection or bus()
    settings = load_settings()
    serial, layout, settings = plan(get_state(connection), settings, action, connector)
    save_settings(settings)
    apply(serial, layout, persist, connection)
