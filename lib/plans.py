"""
Saved trade plans: one file per plan, every save a new version.

A plan is the Trade page as you left it -- instrument, side, the levels, the loss budget,
what you hold and have sold, every skip, the fill depth you picked and the rungs count --
plus a SNAPSHOT of what the page said with it (lots per rung, the two averages, risk and
P&L). The inputs are what a load puts back; the snapshot is what lets a later version be
read against an earlier one, since sizes are always recomputed and the rules can move.

Saving never overwrites. Each save appends a version with a timestamp and a one-line note
("moved stop after CPI"), so a plan is its own history: revisit, change your mind, go
back. A different scenario is a different plan ("... base" / "... hawkish").

Files live in `plans/` at the repo root and are NOT in git (desk, 2026-09-24): they change
constantly and each already keeps its own versions. Archiving moves a file to
`plans/_archive/`. Deleting a version (desk, 2026-09-25) takes it out of the plan but
writes it to `plans/_archive/` first, so nothing here is ever lost for good.

    {"name": "...", "page": "trade", "created": "<iso>",
     "versions": [{"n": 1, "saved_at": "<iso>", "note": "...",
                   "state": {...}, "snapshot": {...}}, ...]}
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

ARCHIVE = "_archive"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slug(name: str) -> str:
    """File stem for a plan name: lower case, runs of anything else become one dash."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def _path(folder: Path, name: str) -> Path:
    return Path(folder) / f"{slug(name)}.json"


def _write(path: Path, data: dict) -> None:
    """Write through a temp file and replace, so a crash mid-save cannot leave half a plan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def list_plans(folder: Path) -> list[dict]:
    """Every live plan, most recently saved first: name, versions, last save time."""
    out = []
    for f in sorted(Path(folder).glob("*.json")) if Path(folder).exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                                  # a broken file is skipped, not fatal
        vs = d.get("versions") or []
        out.append({"name": d.get("name", f.stem), "versions": len(vs),
                    "updated": vs[-1]["saved_at"] if vs else d.get("created", "")})
    return sorted(out, key=lambda p: p["updated"], reverse=True)


def load(folder: Path, name: str) -> dict | None:
    p = _path(folder, name)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def exists(folder: Path, name: str) -> bool:
    return bool(slug(name)) and _path(folder, name).exists()


def create(folder: Path, name: str, state: dict, snapshot: dict, note: str = "") -> dict:
    """A new plan with its first version. Refuses a name already taken -- by slug, so
    "Mar27 fly" and "mar27-fly" are the same plan."""
    if not slug(name):
        raise ValueError("a plan needs a name")
    if exists(folder, name):
        raise FileExistsError(name)
    data = {"name": name.strip(), "page": "trade", "created": _now(), "versions": []}
    return _append(folder, data, state, snapshot, note)


def save_version(folder: Path, name: str, state: dict, snapshot: dict,
                 note: str = "") -> dict:
    """Append a version to an existing plan. Never overwrites an earlier one."""
    data = load(folder, name)
    if data is None:
        raise FileNotFoundError(name)
    return _append(folder, data, state, snapshot, note)


def _append(folder, data, state, snapshot, note) -> dict:
    # One past the highest ever used -- not the count, and not the highest left: once a
    # version can be deleted, either would hand out a number already used. `last_n`
    # remembers a deleted top version.
    n = max([data.get("last_n", 0)] + [v["n"] for v in data["versions"]]) + 1
    data["last_n"] = n
    data["versions"].append({"n": n, "saved_at": _now(), "note": (note or "").strip(),
                             "state": state, "snapshot": snapshot})
    _write(_path(folder, data["name"]), data)
    return data


def archive(folder: Path, name: str) -> Path | None:
    """Move a plan out of the list into `_archive/`, stamped so a later plan of the same
    name cannot collide with it. Recoverable by moving the file back."""
    p = _path(folder, name)
    if not p.exists():
        return None
    dest = Path(folder) / ARCHIVE / f"{p.stem}-{datetime.now():%Y%m%d-%H%M%S}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(dest))
    return dest


def delete_version(folder: Path, name: str, n: int) -> dict:
    """Take version `n` out of a plan. It is written to `_archive/` first, stamped, so it
    can be put back by hand. A plan's only version is not deleted -- archive the plan.
    Numbers are not reused or closed up: v3 stays v3 after v2 goes."""
    data = load(folder, name)
    if data is None:
        raise FileNotFoundError(name)
    keep = [v for v in data["versions"] if v["n"] != n]
    if len(keep) == len(data["versions"]):
        raise KeyError(n)
    if not keep:
        raise ValueError("a plan's only version cannot be deleted; archive the plan")
    gone = next(v for v in data["versions"] if v["n"] == n)
    stem = _path(folder, name).stem
    _write(Path(folder) / ARCHIVE / f"{stem}-v{n}-{datetime.now():%Y%m%d-%H%M%S}.json",
           {"name": data["name"], "deleted_at": _now(), "version": gone})
    data["last_n"] = max([data.get("last_n", 0)] + [v["n"] for v in data["versions"]])
    data["versions"] = keep
    _write(_path(folder, name), data)
    return data
