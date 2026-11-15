#!/usr/bin/env python3
"""Compile po/<lang>.po files into gettext .mo files without needing gettext's msgfmt.

    compile-translations.py OUT_LOCALE_DIR

Writes OUT_LOCALE_DIR/<lang>/LC_MESSAGES/monitor-toggle.mo for every language in po/LINGUAS.
Fuzzy and untranslated entries are skipped, like msgfmt does by default.
"""
import ast
import os
import pathlib
import struct
import sys

PO_DIR = pathlib.Path(__file__).resolve().parent
DOMAIN = "monitor-toggle"


def parse_po(path, keep_untranslated=False):
    catalog, msgid, msgstr, target, fuzzy = {}, None, None, None, False

    def flush():
        if msgid is not None and (keep_untranslated or (msgstr and not fuzzy)):
            catalog[msgid] = msgstr

    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if not line:
            flush()
            msgid = msgstr = target = None
            fuzzy = False
        elif line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("#"):
            continue
        elif line.startswith("msgid "):
            msgid, target = ast.literal_eval(line[6:]), "id"
        elif line.startswith("msgstr "):
            msgstr, target = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"'):
            if target == "id":
                msgid += ast.literal_eval(line)
            else:
                msgstr += ast.literal_eval(line)
    if "" not in catalog:
        raise SystemExit(f"{path}: missing header entry")
    return catalog


def parse_po_template(path):
    """msgids of a .pot file (all untranslated), without the header."""
    return [msgid for msgid in parse_po(path, keep_untranslated=True) if msgid]


def write_mo(catalog, path):
    keys = sorted(catalog)
    ids = [k.encode() for k in keys]
    strs = [catalog[k].encode() for k in keys]
    header_size = 7 * 4
    ids_table = header_size
    strs_table = ids_table + 8 * len(keys)
    data_start = strs_table + 8 * len(keys)
    offsets, blob = [], b""
    for chunk in ids + strs:
        offsets.append((len(chunk), data_start + len(blob)))
        blob += chunk + b"\0"
    out = struct.pack("<7I", 0x950412DE, 0, len(keys), ids_table, strs_table, 0, data_start)
    out += b"".join(struct.pack("<2I", *o) for o in offsets) + blob
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)


def main():
    out_dir = pathlib.Path(sys.argv[1])
    for lang in (PO_DIR / "LINGUAS").read_text().split():
        target = out_dir / lang / "LC_MESSAGES" / f"{DOMAIN}.mo"
        write_mo(parse_po(PO_DIR / f"{lang}.po"), target)
        print(os.fspath(target))


if __name__ == "__main__":
    main()
