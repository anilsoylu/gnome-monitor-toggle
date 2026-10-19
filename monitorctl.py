"""GNOME/Wayland monitör kontrolü için ortak çekirdek.

xrandr Wayland'de çalışmadığı için doğrudan GNOME'un D-Bus arayüzünü
(org.gnome.Mutter.DisplayConfig) kullanır. Hem `monitor` (CLI) hem
`monitor-ui` (GTK arayüzü) bu modülü kullanır.
"""
import json
import os

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.gnome.Mutter.DisplayConfig"
OBJ = "/org/gnome/Mutter/DisplayConfig"
IFACE = "org.gnome.Mutter.DisplayConfig"
STATE = os.path.expanduser("~/.cache/monitor-toggle.json")

TEMPORARY = 1
PERSISTENT = 2


# ---------------------------------------------------------------- D-Bus ----
def proxy():
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, BUS, OBJ, IFACE, None
    )


def get_state(p=None):
    """(serial, monitors, logical_monitors, properties) döner."""
    p = p or proxy()
    return p.call_sync(
        "GetCurrentState", None, Gio.DBusCallFlags.NONE, -1, None
    ).unpack()


def apply(topology, method=TEMPORARY, serial=None, p=None):
    p = p or proxy()
    if serial is None:
        serial = get_state(p)[0]
    params = GLib.Variant.new_tuple(
        GLib.Variant.new_uint32(serial),
        GLib.Variant.new_uint32(method),
        GLib.Variant("a(iiduba(ssa{sv}))", [tuple(lm) for lm in topology]),
        GLib.Variant("a{sv}", {}),
    )
    p.call_sync("ApplyMonitorsConfig", params, Gio.DBusCallFlags.NONE, -1, None)


# ------------------------------------------------------------- yardımcı ----
def enabled_map(logicals):
    """{connector: (x, y, primary)} -- şu an açık olanlar."""
    out = {}
    for x, y, _scale, _tr, primary, mons, _props in logicals:
        for conn in [m[0] for m in mons]:
            out[conn] = (x, y, primary)
    return out


def current_mode(monitors, connector):
    """Monitörün kullanılacak modunu döner.

    Açıksa aktif modu; kapalıysa tercih edilen çözünürlükteki *en yüksek
    tazeleme* modunu (örn. 240Hz yerine 60Hz'e düşmesin diye) seçer.
    """
    for ident, modes, _props in monitors:
        if ident[0] != connector:
            continue
        current = preferred = None
        for mode in modes:
            if mode[6].get("is-current"):
                current = mode
            if mode[6].get("is-preferred"):
                preferred = mode
        if current is not None:
            return current
        if not modes:
            return None
        base = preferred or modes[0]
        same = [
            m
            for m in modes
            if m[1] == base[1] and m[2] == base[2] and "+vrr" not in m[0]
        ]
        if same:
            return max(same, key=lambda m: m[3])
        return base
    return None


def mode_id_for(monitors, connector):
    mode = current_mode(monitors, connector)
    return mode[0] if mode else None


def _mode_size(monitors, connector):
    mode = current_mode(monitors, connector)
    return (mode[1], mode[2]) if mode else (1920, 1080)


# ---------------------------------------------------- temel düzen (topoloji)
def baseline_path():
    return STATE


def _copy_entry(lm):
    """Bir mantıksal monitör girdisinin (değiştirilebilir) kopyasını üretir."""
    entries = [(e[0], e[1], e[2] if len(e) > 2 else {}) for e in lm[5]]
    return [lm[0], lm[1], lm[2], lm[3], lm[4], entries]


def load_baseline():
    """Daha önce görülen tam düzeni {connector: logical_monitor} olarak yükler."""
    if not os.path.exists(STATE):
        return {}
    try:
        with open(STATE) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    baseline = data.get("baseline")
    if not isinstance(baseline, dict):  # eski biçim / bozuk -> yoksay
        return {}
    return {k: _copy_entry(v) for k, v in baseline.items()}


def save_baseline(topo):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as fh:
        json.dump({"baseline": {k: _copy_entry(v) for k, v in topo.items()}}, fh)


def full_topology(monitors, logicals, baseline=None):
    """Açık + kapalı tüm monitörleri içeren tam düzeni üretir.

    Tüm monitörler açıksa canlı düzen esas alınır (ve bu, yeni "temel düzen"
    olarak kaydedilir). Bazı monitörler kapalıysa, konumların tutarlı kalması
    için kayıtlı (baseline) düzen kullanılır; kaydı olmayan monitör sağa eklenir.
    """
    baseline = baseline or {}
    known = [ident[0] for ident, _m, _p in monitors]

    live = {}
    for x, y, scale, tr, primary, mons, _props in logicals:
        for conn in [m[0] for m in mons]:
            live[conn] = [x, y, scale, tr, primary, [(conn, mode_id_for(monitors, conn), {})]]

    if set(known) <= set(live):  # hepsi açık -> canlı düzen doğrudan temel düzen
        return {conn: live[conn] for conn in known}

    topo = {}
    right = 0  # açık/kayıtlı monitörlerin sağ kenarını bul (çakışmayı önler)
    for conn, lm in live.items():
        w, _h = _mode_size(monitors, conn)
        right = max(right, lm[0] + int(w / (lm[2] or 1)))
    for conn, lm in baseline.items():
        if conn in known:
            w, _h = _mode_size(monitors, conn)
            right = max(right, lm[0] + int(w / (lm[2] or 1)))

    for conn in known:
        if conn in baseline:
            topo[conn] = _copy_entry(baseline[conn])
        elif conn in live:
            topo[conn] = live[conn]
        else:
            topo[conn] = [right, 0, 1.0, 0, False, [(conn, mode_id_for(monitors, conn), {})]]
            right += _mode_size(monitors, conn)[0]
        if conn in live:  # güncel mod/çözünürlük her zaman canlıdan alınır
            topo[conn][5] = [(conn, mode_id_for(monitors, conn), {})]
    return topo


def _pack(topo, conns):
    """Seçili connector'ları uygulanabilir bir listeye çevirir (primary + hizalama)."""
    if not conns:
        raise RuntimeError("En az bir monitör açık kalmalı.")
    result = sorted((topo[c] for c in conns), key=lambda lm: (lm[1], lm[0]))
    if not any(lm[4] for lm in result):
        result[0][4] = True
    minx = min(lm[0] for lm in result)
    miny = min(lm[1] for lm in result)
    for lm in result:
        lm[0] -= minx
        lm[1] -= miny
    return result


# ------------------------------------------------------------- üst düzey ----
def set_enabled(connector, enabled, persist=False):
    """Tek bir monitörü aç/kapat."""
    p = proxy()
    serial, monitors, logicals, _props = get_state(p)
    known = [ident[0] for ident, _m, _p in monitors]
    if connector not in known:
        raise RuntimeError(f"'{connector}' bağlı değil.")

    topo = full_topology(monitors, logicals, load_baseline())
    save_baseline(topo)

    conns = set(enabled_map(logicals))
    if enabled:
        conns.add(connector)
    else:
        conns.discard(connector)

    apply(_pack(topo, conns), method=PERSISTENT if persist else TEMPORARY, serial=serial, p=p)


def enable_all(persist=False):
    p = proxy()
    serial, monitors, logicals, _props = get_state(p)
    topo = full_topology(monitors, logicals, load_baseline())
    save_baseline(topo)
    conns = {ident[0] for ident, _m, _p in monitors}
    apply(_pack(topo, conns), method=PERSISTENT if persist else TEMPORARY, serial=serial, p=p)
