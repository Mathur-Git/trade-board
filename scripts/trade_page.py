"""
The Trade page -- one trade on one ladder: how many lots in and out, for a given max loss.

structure_board.py owns the app and the page switcher; this module owns everything on
the Trade page. It exports one thing, TRADE_PAGE, which structure_board.py places in the
layout and shows or hides. The callbacks register themselves with Dash when this module
is imported (`dash.callback`, not `app.callback`), so nothing else has to be wired up.

The arithmetic is not here. lib/ladder.py sizes the way in, lib/exits.py the way out,
lib/cuts.py the cut past the stop, and lib/plans.py keeps saved plans on disk; this file
lays out the page and connects its inputs to them. In file order:

    levels, skips and the grid      helpers the rest of the file leans on
    the ladder and its tables       TRADE_HEAD, _trade_book, _trade_depth_rows
    TRADE_PAGE                      the static layout, the plans panel beside it
    callbacks                       inputs -> stores -> _trade_setup -> draw_trade
    saved plans                     what a save reads and a load writes back

The reasoning behind all of it is in docs/BOARD.md (the Trade sections) and
docs/SCALING.md.
"""

from __future__ import annotations

import math
import socket
from datetime import datetime
from pathlib import Path

from dash import (ALL, Input, Output, State, callback, clientside_callback, ctx, dcc,
                  html, no_update)
from dash.exceptions import PreventUpdate
from flask import has_request_context, request

# lib/ is on sys.path already: structure_board.py puts it there before importing this.
import cuts
import exits
import ladder
import plans

ROOT = Path(__file__).resolve().parents[1]


# -- Levels, skips and the grid ---------------------------------------------------

#: Stand-in stop and target, in rungs from the entry, used only until real ones are
#: typed. Both sit well inside the window: a target on the window's edge reads as the
#: bottom of the ladder rather than as a level someone chose.
PROXY_STOP_TICKS = 4
PROXY_TGT_TICKS = 6
EXIT_SPAN_TICKS = 4     # stand-in rungs from a first exit to flat-by, on the way out


def _key(p: float) -> int:
    """Half-bp ticks as an integer, so a level can be a dict id without float grief."""
    return int(round(p * 2))


def _levels_now(entry, stop, side: str) -> list[float]:
    """The rungs as the page would draw them, standing in for a missing stop.

    Both the click handler and the renderer need this, and they must agree: if they
    disagreed about which rungs exist, a click on an end rung would skip it in one and
    unskip it in the other.
    """
    entry, stop = _fnum(entry), _fnum(stop)
    if entry is None:
        return []
    sgn = ladder.sign(side)
    if stop is None or sgn * (entry - stop) <= 0:
        stop = round(entry - sgn * PROXY_STOP_TICKS * ladder.TICK, 6)
    return ladder.entry_levels(entry, stop, side)


def _effective_out_skips(levels: list[float], store, defaults) -> set[float]:
    """Pulled exit rungs: the default, plus what you pulled, less what you put back."""
    store = store or {}
    off = {round(float(x), 6) for x in store.get("off", [])}
    on = {round(float(x), 6) for x in store.get("on", [])}
    return ((defaults(levels) | off) - on) & set(levels)


def _trade_default_in_skips(levels: list[float]) -> set[float]:
    """Trade, way in: only the rung right above the stop is pulled by default. The entry
    rung is worked (desk, 2026-09-24). Held off below three rungs, so two are always
    worked."""
    return {levels[-1]} if len(levels) >= 3 else set()


def _trade_effective_in_skips(levels: list[float], store) -> set[float]:
    store = store or {}
    off = {round(float(x), 6) for x in store.get("off", [])}
    on = {round(float(x), 6) for x in store.get("on", [])}
    return (_trade_default_in_skips(levels) | off) - on


def _no_default(levels: list[float]) -> set[float]:
    """Trade, way out: nothing is pulled by default (desk, 2026-09-24)."""
    return set()


def _toggle_skip(store, lv: float, auto: set[float]) -> dict:
    """One click on a rung's size: pull it, or put it back.

    The scale-in's bookkeeping exactly: `off` holds rungs you pulled, `on` holds
    default-pulled rungs you put back, and the defaults themselves are derived, so a
    click on a default reads as "put this back" rather than "pull it again".
    """
    store = store or {}
    off = {round(float(x), 6) for x in store.get("off", [])}
    on = {round(float(x), 6) for x in store.get("on", [])}
    skipped = (lv in auto or lv in off) and lv not in on
    off.discard(lv)
    on.discard(lv)
    if skipped and lv in auto:
        on.add(lv)
    elif not skipped and lv not in auto:
        off.add(lv)
    return {"off": sorted(off), "on": sorted(on)}


def _filter_skips(store, alive) -> dict:
    """Drop only the choices whose rung no longer exists -- filter, do not wipe."""
    store = store or {}
    return {"off": [x for x in store.get("off", []) if x in alive],
            "on": [x for x in store.get("on", []) if x in alive]}


def _levels_of(store) -> dict:
    """A per-rung store (half-bp tick -> lots) as {price: lots}."""
    return {int(k) / 2.0: int(v) for k, v in (store or {}).items() if v}


def _gather(vals, ids, cur) -> dict:
    """Per-rung boxes into one map. Unchanged stops here, or box and store spin forever.
    Rungs scrolled out of the window keep their entry: the lots are still real."""
    out = dict(cur or {})
    for v, i in zip(vals, ids):
        key = str(i["p"])
        if v and int(v) > 0:
            out[key] = int(v)
        else:
            out.pop(key, None)
    if out == (cur or {}):
        raise PreventUpdate
    return out


def _snap(x):
    """Onto the 0.5bp grid. A price between rungs cannot be drawn -- the ladder has no
    row for it, so its lots, flags and market line silently vanish -- and a typed level
    that is not on the grid is almost always a slip. So the page works from the nearest
    rung, and the box underneath says so ("using 21")."""
    return None if x is None else round(round(x / ladder.TICK) * ladder.TICK, 6)


def _d0(v) -> str:
    """Dollars to the nearest one, never "-0": a figure that rounds to nothing is 0."""
    return f"{0.0 if abs(v) < 0.5 else v:,.0f}"


def _px3(v) -> str:
    """A price to three decimals with the trailing zeros off: 1.341, 20.5, 21."""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _first_profit(avg: float, side: str) -> float:
    """The first rung that is a profit on `avg`: the lowest first exit a long can take
    and still make money on every lot it sells (the highest, for a short)."""
    t = ladder.TICK
    k = (math.floor(avg / t) + 1) if side == "buy" else (math.ceil(avg / t) - 1)
    return round(k * t, 6)


def _window(anchor: float, side: str, ticks: int) -> tuple[float, float]:
    """Lowest and highest rung drawn. Asymmetric by one tick, on purpose.

    The market line, not the anchor row, is what sits dead centre: above the anchor when
    buying and below it when selling. That puts one more rung on the far side of the
    anchor than the near side, and leaves `ticks` either side of the line.

    The Trade page anchors on the MARK, so the line is the thing you typed rather than a
    thing derived -- long marks to the bid, short to the ask, each being the price you
    could get out at.
    """
    up = ticks if side == "buy" else ticks - 1
    dn = ticks - 1 if side == "buy" else ticks
    return round(anchor - dn * ladder.TICK, 6), round(anchor + up * ladder.TICK, 6)


def _fnum(x):
    """Read a level off a text field. Blank, partial ("-", ".") and junk all read None.

    These fields are text rather than number inputs on purpose: a number input paints a
    negative VALUE in accounting style, so a stop of -10 appears as "(10)". Placeholders
    escape it, which is why a stand-in looked right and a typed or dragged level did
    not. Text inputs paint exactly the characters they hold.
    """
    if x is None:
        return None
    t = str(x).strip().replace(",", "")
    if not t or t in ("-", "+", ".", "-.", "+."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _num(cid: str, value, step: float, mn=None, placeholder=None):
    """A panel field. Commits half a second after you stop typing, not on blur.

    Safe here and NOT safe for the held boxes: these live outside the part of the page
    the render callback rebuilds, so a commit cannot yank the cursor out from under you
    mid-number. The held boxes sit inside the ladder, which is rebuilt on every change,
    so they wait for blur.
    """
    extra = {"placeholder": placeholder} if placeholder else {}
    return dcc.Input(id=cid, type="text", inputMode="decimal", value=value,
                     debounce=0.5, className="lad-input", **extra)


#: Which marker column a chip sits in on the Trade ladder. IN is where the position
#: comes from -- the entry and the stop. OUT is where it goes -- the first exit and the
#: target it is flat by. One shared gutter put ENTRY and 1ST side by side on the same
#: rung and read as one thing. OUT BY sits with the stop, under it (desk, 2026-09-30):
#: the losing side's levels read down one column.
OUT_KINDS = {"first", "target"}


def _split_tags(tags):
    return ([t for t in tags if t[0] not in OUT_KINDS],
            [t for t in tags if t[0] in OUT_KINDS])


def _rule_at(grid: list[float], value) -> tuple[float | None, float]:
    """The row a rule at `value` falls in, and how far down it, from the row's centre --
    where the price is written. The averages are almost never on a rung."""
    if value is None or value != value:
        return None, 0.0
    for lv in grid:
        if lv - ladder.TICK / 2 < value <= lv + ladder.TICK / 2:
            return lv, 0.5 + (lv - value) / ladder.TICK
    return None, 0.0


def _px_cell(lv: float, rules) -> html.Td:
    """The price spine, with any rule -- (row, fraction, class) -- that falls in it."""
    kids = [html.Span(f"{lv:.1f}", className="lad-px")]
    for row, frac, klass in rules:
        if row is not None and abs(lv - row) < 1e-9:
            kids.append(html.Div(className=klass, style={"top": f"{frac * 100:.2f}%"}))
    return html.Td(kids, className="lad-px-c")


def _settle_marked(lp: dict, settle, sgn: int) -> float | None:
    """What the statement already shows for this trade at `settle` (desk, 2026-10-01):
    the books mark to market every day, so they read as if the position were put on at
    settle. That is what is banked from sales, plus the lots still on marked from their
    average to settle. Filled and Sold are taken as the book at settle; lots the ladder
    adds later go on at their own rung, which is how they will reach the statement.

    Every whole-trade figure from settle is the same figure from entry less this one
    number -- a reference, nothing sized on it. None with no settle typed."""
    if settle is None:
        return None
    held = (lp["held"] * sgn * (settle - lp["held_avg"]) * lp["dollars_per_bp"]
            if lp["held"] and lp["held_avg"] is not None else 0.0)
    return lp["banked"] + held


def _exit_rows(p: dict, stop_word: str = "if stopped") -> list:
    """The reversal table: if it turns at each rung, what is banked and what is left.
    With a cut past the stop, the stop-side column is what the rest loses cut through
    OUT BY, and its head says so ("if cut")."""
    head = html.Tr(className="lad-head", children=[
        html.Th("reaches"), html.Th("sell"), html.Th("left"), html.Th("avg out"),
        html.Th("banked"), html.Th(stop_word), html.Th("if runs"),
    ])
    out = [head]
    last = p["rows"][-1]["depth"] if p["rows"] else 0
    for r in p["rows"]:
        cls = " ".join(x for x in ("lad-full" if r["depth"] == last else "",
                                   "ex-free-row" if r["free"] else "") if x)
        label = "now" if r["depth"] == 0 else f"{r['level']:.1f}"
        out.append(html.Tr(className=cls, children=[
            html.Td(label, className="lbl"),
            html.Td(f"{r['lots']:,}" if r["lots"] else "—", className="val"),
            html.Td(f"{r['left']:,}", className="val"),
            html.Td("—" if r["sold"] == 0 else f"{r['avg_out']:.3f}", className="val"),
            html.Td(_d0(r["realised"]), className="val pos"),
            html.Td(_d0(r["if_stopped"]),
                    className="val " + ("pos" if r["if_stopped"] > -0.5 else "neg")),
            html.Td(_d0(r["if_runs"]), className="val rr"),
        ]))
    return out



def _lvl(cid: str) -> html.Td:
    """One typed level in the inputs table, with a line under it for the value the
    ladder is actually USING when yours is missing or has been replaced. The line always
    keeps its height, so the table does not move as you type."""
    return html.Td(className="lvl-cell", children=[
        _num(cid, None, ladder.TICK), html.Div(id=f"{cid}-use", className="lvl-use")])


def _lvl_table(prefix: str, rows) -> html.Table:
    """The levels as a table: IN beside OUT, so each level sits next to its partner --
    entry with first exit, stop with the level you are flat by -- and the two averages
    they produce underneath. `rows` are (label, in-cell, out-cell); a cell of None is
    blank, a string is a section heading spanning the row."""
    body = []
    for label, a, b in rows:
        if a is None and b is None:
            body.append(html.Tr(className="lvl-sect", children=[
                html.Th(label, colSpan=3)]))
            continue
        body.append(html.Tr([html.Td(label, className="lbl"),
                             a if a is not None else html.Td(),
                             b if b is not None else html.Td()]))
    return html.Table(className="lvl-table", id=f"{prefix}-levels", children=[
        html.Thead(html.Tr([html.Th(""), html.Th("in"), html.Th("out")])),
        html.Tbody(body)])


def _avg_cell(cid: str, klass: str) -> html.Td:
    return html.Td(id=cid, className=f"lvl-avg {klass}", children="—")


def _use_text(typed, used) -> str:
    """What goes under a box: the value in use, but only when it REPLACED one you typed.

    An empty box already shows its stand-in as the greyed placeholder, so a line under
    it only said the same number twice (desk, 2026-09-24). Where the line earns its
    place is a typed level the page could not use -- a first exit that is not a profit
    on the average -- because the box still shows your number.
    """
    t = _fnum(typed)
    if used is None or t is None or abs(t - used) < 1e-9:
        return ""
    return f"using {used:g}"


# ---------------------------------------------------------------------------
# The Trade page: one ladder, both halves of a trade.
#
# The scale-in and the scale-out are the same trade seen from opposite ends, and the
# desk thinks about them together. Splitting them across two pages meant retyping the
# position and reading an average off one screen to enter it on another.
#
# No new arithmetic. `ladder.plan` sizes the way in against a loss budget, `exits.plan`
# partitions the way out, and this page is the join between them. Flipping is NOT here:
# the desk dropped it (2026-09-25), and the Exit page that carried it went with it.
#
# The join is the fill depth. A scale-in does not produce ONE position, it produces a
# position per depth, which is the whole argument for the fill-depth table. So the exit
# half sizes whichever depth you pick: click a row and the way out re-sizes to the
# position and average that row leaves you holding.
# ---------------------------------------------------------------------------

TRADE_WINDOW_TICKS = 10     # the default (desk, 2026-09-25); the rungs counter moves it
TRADE_RUNGS_MIN, TRADE_RUNGS_MAX = 8, 18

TRADE_HEAD = html.Thead(html.Tr(className="lad-head", children=[
    html.Th("", className="lad-mark-c mk-in"),
    html.Th("", className="lad-mark-c mk-out"),
    # FILLED, not "Held" (desk, 2026-09-25): the lots already taken. Code, stores and
    # saved plans keep the name `held`, so plans saved before the rename still load.
    html.Th("Filled", className="lad-held-c"),
    # IN and OUT each head their size AND its bar: the bars sit by their own numbers on
    # both sides now, so "bids" and "asks" named the wrong book on a short (desk,
    # 2026-09-25).
    html.Th("In", className="tr-in-c tr-span", colSpan=2),
    html.Th(className="lad-px-c lad-px-head", children=dcc.Input(
        id="tr-mark", type="text", inputMode="decimal", value=None, debounce=0.5,
        placeholder="bid", className="lad-entry-in")),
    html.Th("Out", className="tr-out-c tr-span", colSpan=2),
    html.Th("Sold", className="lad-held-c ex-sold-c"),
    html.Th("Pos", className="tr-pos-c"),
    html.Th("Left", className="tr-left-c"),
    # No Risk $ or Banked $ here (desk, 2026-09-25): they repeated the LOSS column of the
    # fill-depth table and the BANKED column of the way-out table, rung for rung.
    # FILLED RISK and IN RISK are not that Risk $ back (desk, 2026-09-25). It was the
    # running loss by depth; these are each rung's OWN dollars to the stop, held lots and
    # lots still to work apart, which nothing else on the page shows.
    html.Th("Filled risk", className="tr-risk-c tr-risk-f"),
    html.Th("In risk", className="tr-risk-c"),
    # OUT REGRET (desk, 2026-09-29; it was OUT P&L): each out rung's own dollars to the
    # target -- the upside its lots give up if the move runs on. It is what equal regret
    # splits evenly and the out peak bends, as IN RISK is for the way in. The P&L it
    # replaced is still the fill-depth table's P&L and the way-out table's BANKED.
    html.Th("Out regret", className="tr-risk-c tr-risk-o"),
    # The peak's gold dot (desk, 2026-09-27), in a ruled column of its own at the far right,
    # as on the fill-depth table: click a rung you add at to centre the risk there, click
    # it again to clear. The way out's blue dot beside it (desk, 2026-09-29) does the same
    # on the rungs you sell at.
    html.Th("●", className="tr-peak-c", title="peak in"),
    html.Th("●", className="tr-peak-c tr-peak-out-c", title="peak out"),
]))

#: Columns left of FILLED RISK, which the ladder's foot rows span with their label.
TRADE_LABEL_SPAN = 11


def _risk_txt(v: float) -> str:
    """A rung's dollars to the stop, blank where it rounds to nothing."""
    return "" if abs(v) < 0.5 else _d0(v)


def _trade_marks(tags, side, lo, hi, entry, stop, first, target, avg, out_by=None):
    """Marker chips. The levels that define the trade drag; the rest are computed.

    The first exit is bounded by the AVERAGE, not by the entry. Scaling a long down pulls
    the average below the entry, so everything between the two is already profit and there
    is no reason to refuse it -- you can start working out as soon as the book is onside,
    which is often well before the market is back to where you started. The entry is
    therefore not capped by the first exit either; the two are free to cross.

    What is NOT negotiable is the stop, which stays on the losing side of the entry, and
    the target, which stays beyond the first exit -- it is the boundary you are flat by.
    OUT BY stays at least a rung past the stop, and the stop short of it, so the cut
    always has a rung. AVG and FREE fall out of the sizing, so there is nowhere to drag
    them to.
    """
    t = ladder.TICK
    if side == "buy":                      # out_by < stop < entry ; avg < first < target
        band = {"stop":   (lo if out_by is None else round(out_by + t, 6),
                           round(entry - t, 6)),
                "entry":  (round(stop + t, 6), hi),
                "first":  (_first_profit(avg, "buy"), round(target - t, 6)),
                "target": (round(first + t, 6), hi),
                "outby":  (lo, round(stop - t, 6))}
    else:                                  # entry < stop < out_by ; target < first < avg
        band = {"stop":   (round(entry + t, 6),
                           hi if out_by is None else round(out_by - t, 6)),
                "entry":  (lo, round(stop - t, 6)),
                "first":  (round(target + t, 6), _first_profit(avg, "sell")),
                "target": (lo, round(first - t, 6)),
                "outby":  (round(stop + t, 6), hi)}
    ids = {"stop": "tr-stop", "entry": "tr-entry",
           "first": "tr-first", "target": "tr-target", "outby": "tr-outby"}
    out = []
    for kind, text in tags:
        b = band.get(kind)
        if b and b[0] <= b[1]:
            out.append(html.Span(text, className="lad-tag lad-flag", **{
                "data-kind": kind, "data-input": ids[kind],
                "data-lo": f"{b[0]:g}", "data-hi": f"{b[1]:g}"}))
        else:
            out.append(html.Span(text, className="lad-tag", **{"data-kind": kind}))
    return out


def _trade_book(lp, ep, side, mark, avg, held_map, sold_map, in_excl,  # noqa: C901
                out_excl, ticks=TRADE_WINDOW_TICKS, sel=None, peak=None, shape_on=False,
                peak_out=None, shape_out_on=False, cp=None, risk_ref=None):
    """One ladder carrying both halves of the trade, and the cut past the stop.

    The cut (desk, 2026-09-30) sits in `Out` too, on the rungs from one past the stop to
    OUT BY: cutting a long is selling it, so it is the same column, marked with a red rule
    where the way out has its green one. `Left` counts down to nothing at OUT BY. The two
    never share a rung -- the way out starts above the average, the cut below the stop.
    `cp` is the cut for the depth picked (lib/cuts.py), None with no OUT BY; `risk_ref`
    the price the risk columns measure to, the stop or, with a cut, its average.

    `In` is what the scale-in adds at a rung, `Out` what the exit sells at one. They
    never collide: in-rungs run from the entry toward the stop and out-rungs from the
    first exit toward the target, so the price spine separates them by construction.

    They can now OVERLAP, because the first exit is bounded by the average rather than
    the entry: a long scaled down to an average of 20.2 may start working out at 20.5,
    which is also a rung it adds on. That is coherent -- you add there on the way down and
    sell there on the way back up, which is exactly what the two columns already say --
    but it means a price no longer belongs to one half, so the skips are two stores and
    the position is two columns.

    `Pos` is what you have accumulated at that price on the way in; `Left` is what remains
    after selling at it on the way out. One column serving both was fine while the halves
    could not collide and is wrong now.

    `Sold` sits outside `Out` as `Held` sits outside `In`: what you have already done,
    beside what the plan does next. Rungs behind the furthest sale are drawn as passed.

    The bars follow the side you would actually work: a long adds on the bid and sells
    on the ask, a short adds on the offer and covers on the bid. So the two halves fall
    on opposite sides of the spine without being told to.
    """
    entry, stop = lp["entry"], lp["stop"]
    first, target = ep["first"], ep["last"]
    out_by = cp["out_by"] if cp else None
    risk_ref = stop if risk_ref is None else risk_ref

    in_q = dict(zip(lp["levels"], lp["lots"]))
    out_q = dict(zip(ep["levels"], ep["lots"]))
    in_at = {r["level"]: r for r in lp["rows"] if not r["held"] and r["depth"] > 0}
    out_at = {r["level"]: r for r in ep["rows"] if r["depth"] > 0}
    cut_q = dict(zip(cp["levels"], cp["lots"])) if cp else {}
    cut_left = dict(zip(cp["levels"], cp["left"])) if cp else {}
    held_map = held_map or {}
    sold_map = sold_map or {}
    passed = set(ep["passed"]) | set(cp["passed"] if cp else ())

    lo, hi = _window(mark, side, ticks)
    n = int(round((hi - lo) / ladder.TICK))
    grid = [round(hi - i * ladder.TICK, 6) for i in range(n + 1)]
    big_in = max(lp["lots"]) if lp["lots"] else 0
    big_out = max(ep["lots"]) if ep["lots"] else 0
    big_cut = max(cp["lots"]) if cp and cp["lots"] else 0

    # Two rules at their true heights: the average in (red) and, once there is a
    # position to sell, the average the way out takes it out at (green).
    avg_row, avg_frac = _rule_at(grid, avg)
    out_avg = ep["avg_out"] if avg is not None else None
    out_row, out_frac = _rule_at(grid, out_avg)
    rules = [(avg_row, avg_frac, "lad-avgline"), (out_row, out_frac, "lad-avgline out")]

    # What each rung loses if the stop trades: FILLED RISK on the lots filled there (skipped
    # rungs too -- a held lot is risk wherever it sits), IN RISK on the lots still to work.
    # With a cut, to the cut's average: where, for sizing, the whole book is stopped.
    dpb, sgn = lp["dollars_per_bp"], ladder.sign(side)
    held_lv = {_key(p): (p, q) for p, q in lp["held_levels"].items()}

    def risk_at(lv, q):
        return q * sgn * (lv - risk_ref) * dpb

    def pnl_at(lv, q):
        return q * sgn * (lv - ep["avg"]) * dpb

    def regret_at(lv, q):
        return exits.regret_at(lv, q, target, side, dpb)

    # Which lots the exit is sized for: In rungs deeper than the picked depth are NOT in
    # it, so their size, bar, Pos and In risk grey out. (A dashed "sized to here" line was
    # tried and dropped, desk 2026-09-24.)
    rows = []
    for lv in grid:
        qi, qo = in_q.get(lv, 0), out_q.get(lv, 0)
        r_in = in_at.get(lv)
        unc = r_in is not None and sel is not None and r_in["depth"] > sel
        work_in = lv in lp["all_levels"]
        work_out = lv in ep["ahead"]
        # A cut rung, unless the way out is on it -- only an average dragged below the
        # stop by fills typed past it could put them together, and the way out wins.
        work_cut = lv in cut_q and not work_out
        qc = cut_q.get(lv, 0) if work_cut else 0
        skip_in = work_in and lv in in_excl
        skip_out = work_out and lv in out_excl
        cls, tags = ["lad-row"], []
        # Dimmed as passed only where nothing is still worked going in: a rung you are
        # still adding at is live, whatever the way out has been through.
        if lv in passed and not work_in:
            cls.append("ex-passed")

        if abs(lv - mark) < 1e-9:
            cls += ["ex-mkt", "lad-mkt-above" if side == "buy" else "lad-mkt-below"]
        if abs(lv - entry) < 1e-9:
            cls.append("lad-entry")
            tags.append(("entry", "ENTRY"))
        # No AVG chip on either side: the red and green rules show where the averages
        # are, and the levels table says what they are. A word beside them was noise.
        if avg_row is not None and abs(lv - avg_row) < 1e-9:
            cls.append("lad-avg")
        if abs(lv - stop) < 1e-9:
            cls.append("lad-stop")
            tags.append(("stop", "STOP"))
        if abs(lv - first) < 1e-9:
            cls.append("ex-first")
            tags.append(("first", "1ST"))
        if abs(lv - target) < 1e-9:
            cls.append("lad-tgt")
            tags.append(("target", "TGT"))
        if out_by is not None and abs(lv - out_by) < 1e-9:
            cls.append("lad-outby")
            tags.append(("outby", "OUT BY"))
        # No FREE marker on this ladder (desk, 2026-09-24): the "if stopped" column of
        # the way-out table already shows where the trade stops being able to lose.
        tags_in, tags_out = _split_tags(tags)
        # Strike the price only when the rung carries no size at all. With the halves
        # overlapping, one side skipped and the other live is a rung you still work.
        if (skip_in or skip_out) and not (qi or qo):
            cls.append("lad-skip")
        if qi or qo or qc:
            cls.append("lad-live")
        if work_in or work_out or work_cut:
            cls.append("lad-work")

        wi = f"{100.0 * qi / big_in:.1f}%" if big_in and qi else "0%"
        wo = f"{100.0 * qo / big_out:.1f}%" if big_out and qo else "0%"
        wc = f"{100.0 * qc / big_cut:.1f}%" if big_cut and qc else "0%"
        bar_in = html.Div(className="lad-barwrap" + (" tr-unc" if unc else ""),
                          children=[html.Div(
            className="lad-bar bid" if side == "buy" else "lad-bar ask",
            style={"width": wi})])
        bar_out = html.Div(className="lad-barwrap", children=[html.Div(
            className="lad-bar ask" if side == "buy" else "lad-bar bid",
            style={"width": wc if work_cut else wo})])
        empty = html.Div(className="lad-barwrap")
        # Each bar sits beside its own numbers, whatever the side: the way-in bar by IN on
        # the left, the way-out bar by OUT on the right (desk, 2026-09-25). On a short the
        # book would put selling in on the ask, but a bar across the spine from its size
        # read as belonging to the other half. The colour still says buy or sell. A cut
        # is a sale out of the position too, so its bar is the way out's, scaled to the
        # cut's own biggest rung.
        on_bid, on_ask = bar_in, bar_out
        show_bid, show_ask = work_in, work_out or work_cut

        held = html.Td(className="lad-held-c", children=dcc.Input(
            id={"type": "tr-held", "p": _key(lv)}, type="number", min=0, step=1,
            value=held_map.get(str(_key(lv))), debounce=True, className="lad-held-in"))
        sold = html.Td(className="lad-held-c ex-sold-c", children=dcc.Input(
            id={"type": "tr-sold", "p": _key(lv)}, type="number", min=0, step=1,
            value=sold_map.get(str(_key(lv))), debounce=True, className="lad-held-in"))

        def cell(q, skipped, workable, klass, kind):
            txt = "skip" if skipped else (f"{q:,}" if q else "")
            # A skip is marked on its OWN cell. Styled from the row, a skip on a rung that
            # was live on the other side came out bold like a size (desk, 2026-09-24).
            if skipped:
                klass = f"{klass} is-skip"
            if workable:
                # The rule on the cell's outer edge says this rung is in THIS half. It
                # was keyed to the row, so a rung worked in either half drew both
                # (desk, 2026-09-25).
                return html.Td(txt, className=f"{klass} tr-work clickable",
                               id={"type": f"tr-skip-{kind}", "p": _key(lv)},
                               n_clicks=0)
            return html.Td(txt, className=klass)

        # Two positions, because a rung can now be in both halves: what has accumulated
        # on the way in, and what is left after selling on the way out -- or cutting.
        pos_txt = f"{in_at[lv]['pos']:,}" if lv in in_at else ""
        left_txt = (f"{out_at[lv]['left']:,}" if lv in out_at
                    else f"{cut_left[lv]:,}" if work_cut and cp["position"] else "")
        # The cut's size: shown, never clicked -- the cut has no skips.
        out_cell = (html.Td(f"{qc:,}" if qc else "", className="tr-out-c tr-cut")
                    if work_cut else cell(qo, skip_out, work_out, "tr-out-c", "out"))
        h_risk = risk_at(lv, held_lv.get(_key(lv), (lv, 0))[1])
        i_risk = risk_at(lv, qi)
        o_regret = regret_at(lv, qo)

        # The peak's dot: clickable on the rungs you add at while the peak is on; kept but
        # dimmed while it is off, or while the rung it marks is off the way in. Empty
        # otherwise: hollow circles on every pickable rung were tried and dropped (desk,
        # 2026-09-27); the column's own rule is what makes it findable.
        is_peak = peak is not None and abs(lv - peak) < 1e-9
        dot_cls = "tr-peak-c" + ("" if lp["peak"] is not None else " is-off")
        if shape_on and work_in:
            dot = html.Td("●" if is_peak else "", className=f"{dot_cls} clickable",
                          id={"type": "tr-peak", "p": _key(lv)}, n_clicks=0)
        else:
            dot = html.Td("●" if is_peak else "", className=dot_cls)
        # The way out's blue dot, the same on the rungs still ahead of you on the way out.
        is_peak_o = peak_out is not None and abs(lv - peak_out) < 1e-9
        dot_o_cls = "tr-peak-c tr-peak-out-c" + ("" if ep["peak"] is not None else " is-off")
        if shape_out_on and work_out:
            dot_o = html.Td("●" if is_peak_o else "", className=f"{dot_o_cls} clickable",
                            id={"type": "tr-peak-out", "p": _key(lv)}, n_clicks=0)
        else:
            dot_o = html.Td("●" if is_peak_o else "", className=dot_o_cls)

        rows.append(html.Tr(className=" ".join(cls), children=[
            html.Td(_trade_marks(tags_in, side, lo, hi, entry, stop, first, target,
                                 avg if avg is not None else entry, out_by),
                    className="lad-mark-c mk-in"),
            html.Td(_trade_marks(tags_out, side, lo, hi, entry, stop, first, target,
                                 avg if avg is not None else entry, out_by),
                    className="lad-mark-c mk-out"),
            held,
            cell(qi, skip_in, work_in, "tr-in-c" + (" tr-unc" if unc else ""), "in"),
            html.Td(on_bid if show_bid else empty, className="lad-bid-c"),
            _px_cell(lv, rules),
            html.Td(on_ask if show_ask else empty, className="lad-ask-c"),
            out_cell,
            sold,
            html.Td(pos_txt, className="tr-pos-c" + (" tr-unc" if unc else "")),
            html.Td(left_txt, className="tr-left-c"),
            html.Td(_risk_txt(h_risk), className="tr-risk-c"),
            html.Td(_risk_txt(i_risk), className="tr-risk-c" + (" tr-unc" if unc else "")),
            html.Td(_risk_txt(o_regret), className="tr-risk-c"),
            dot,
            dot_o,
        ]))

    # The foot: what the rungs drawn do not show, then the totals. Held risk is taken
    # before any sales, so the sales come off in a line of their own -- they leave at the
    # held average, not off a rung -- and the two totals together are the full-fill LOSS.
    # OUT REGRET totals with what the sales already gave up, so it is everything the way
    # out leaves short of holding the whole position to the target. The label's "if it
    # works" is still the P&L -- what the way out banks.
    shown = {_key(lv) for lv in grid}
    held_tot = sum(risk_at(p, q) for p, q in held_lv.values())
    in_tot = sum(risk_at(p, q) for p, q in zip(lp["levels"], lp["lots"]))
    held_off = sum(risk_at(p, q) for k, (p, q) in held_lv.items() if k not in shown)
    in_off = sum(risk_at(p, q) for p, q in zip(lp["levels"], lp["lots"])
                 if _key(p) not in shown)
    sold_off = ((lp["sold"] * sgn * (lp["held_avg"] - risk_ref) * dpb + lp["banked"])
                if lp["sold"] else 0.0)
    out_pnl = sum(pnl_at(p, q) for p, q in zip(ep["levels"], ep["lots"]))
    out_tot = sum(regret_at(p, q) for p, q in zip(ep["levels"], ep["lots"]))
    out_off = sum(regret_at(p, q) for p, q in zip(ep["levels"], ep["lots"])
                  if _key(p) not in shown)
    banked = ep["banked"] if ep["sold"] else 0.0
    sold_regret = sum(regret_at(p, q) for p, q in ep["sold_levels"].items())

    def foot(label, h, i, o, klass=""):
        return html.Tr(className=f"tr-risk-foot {klass}".rstrip(), children=[
            html.Td(label, colSpan=TRADE_LABEL_SPAN, className="tr-risk-lbl"),
            html.Td(_risk_txt(h), className="tr-risk-c"),
            html.Td(_risk_txt(i), className="tr-risk-c"),
            html.Td(_risk_txt(o), className="tr-risk-c"),
            html.Td("", className="tr-peak-c"),
            html.Td("", className="tr-peak-c tr-peak-out-c")])

    if any(abs(x) >= 0.5 for x in (held_tot, in_tot, out_tot, banked, sold_regret)):
        if any(abs(x) >= 0.5 for x in (held_off, in_off, out_off)):
            rows.append(foot("off the ladder", held_off, in_off, out_off))
        if lp["sold"]:
            rows.append(foot("sold / banked", -sold_off, 0.0, sold_regret))
        held_net = held_tot - sold_off
        word = "if cut" if cp else "if stopped"
        rows.append(foot(f"total  ·  {word} {_d0(held_net + in_tot)}  ·  "
                         f"if it works {_d0(out_pnl + banked)}", held_net, in_tot,
                         out_tot + sold_regret, "tr-risk-total"))
    return rows


def _depth_label(sel, depths: list, held: bool) -> str:
    """The picked depth in words: "filled only", "filled + 2 rungs", "2 rungs", "full fill".
    "filled to 0" said the same thing in a way nobody reads."""
    if sel is None or not depths:
        return "—"
    if sel == 0:                      # before "full fill": with no rungs to add, a
        return "filled only"          # book of filled lots is still only what is filled
    if sel == depths[-1]:
        return "full fill"
    n = f"{sel} rung{'s' if sel != 1 else ''}"
    return f"filled + {n}" if held else n


def _trade_depth_rows(lp: dict, sel, banks: dict) -> list:
    """The fill-depth table, with every row a choice.

    Clicking one says "suppose it filled this far", and the exit half re-sizes to the
    position and average that row leaves you on. The selected row is what the rest of
    the right-hand side is then describing. It is marked by a gold dot in a column of
    its own, left of `filled`, and a blue fill (desk, 2026-09-25: the dot replaces the
    thin accent bar on the row's left edge).

    P&L is what the way out BANKS from that depth -- `banks`, one exit plan per row --
    not the whole position valued at the target. The target is the level you are flat
    by, so the exit ladder never sells there, and pricing every lot at it overstated
    the reward by about half: $15,875 against the $10,762 the exit beside it banks.
    """
    head = html.Tr(className="lad-head", children=[
        html.Th("", className="dot"), html.Th("depth"), html.Th("lots"), html.Th("pos"), html.Th("avg"),
        html.Th("loss"), html.Th("P&L"), html.Th("R:R"),
    ])
    out = [head]
    last = lp["rows"][-1]["depth"] if lp["rows"] else 0
    for r in lp["rows"]:
        cls = [x for x in ("lad-full" if r["depth"] == last else "",
                           "lad-held-row" if r["held"] else "") if x]
        if r["depth"] == sel:
            cls.append("tr-picked")
        elif sel is not None and r["depth"] > sel:
            cls.append("tr-uncounted")        # not in the position the exit is sized for
        label = (f"filled @ {_px3(r['level'])}" if r["held"]
                 else f"{r['depth']} @ {r['level']:.1f}")
        pnl = banks.get(r["depth"])
        pnl = float("nan") if pnl is None else pnl
        rr = pnl / r["loss"] if r["loss"] > 0 else float("nan")

        def num(v, fmt, k):
            ok = v == v and v not in (float("inf"), float("-inf"))
            txt = (_d0(v) if fmt == ",.0f" else format(v, fmt)) if ok else "-"
            return html.Td(txt, className=f"val {k}" if ok else "val")

        out.append(html.Tr(
            className=" ".join(cls + ["clickable"]),
            id={"type": "tr-depth", "d": r["depth"]}, n_clicks=0,
            children=[
                html.Td("●" if r["depth"] == sel else "", className="dot"),
                html.Td(label, className="lbl"),
                html.Td(f"{r['lots']:,}", className="val"),
                html.Td(f"{r['pos']:,}", className="val"),
                num(r["avg"], ".3f", ""),
                num(r["loss"], ",.0f",
                    "neg" if r["loss"] > 0 else ("pos" if r["loss"] < 0 else "")),
                num(pnl, ",.0f", "pos" if pnl and pnl > 0 else ""),
                num(rr, ".2f", "rr"),
            ]))
    return out


#: Saved plans get a panel of their own, to the right of the Trade panel (desk,
#: 2026-09-24) -- not squeezed into the tables. Plans and their versions are LISTS you
#: click, not dropdowns: every saved plan and every version is in view at once, and a
#: list takes the board's own colours in both themes. Newest first in both.
PLANS_PANEL = html.Div(className="chart-card panel plan-panel", children=[
    # One compact button style throughout (desk, 2026-09-25): New and Reset in the head,
    # Save as new under it, Archive by the plan list, Delete by the versions. Save version
    # is in the Trade panel's head (desk, 2026-10-08), over All clear.
    html.Div(className="plan-head", children=[
        html.Div(className="plan-row", children=[
            html.Div("Plans", className="card-title"),
            html.Div(className="plan-head-btns", children=[
                # Undo every change since the version the page came from (desk,
                # 2026-09-25). Live only while there are changes to undo; it says which
                # version it goes to. Beside New (desk, 2026-10-08), not a row of its own.
                html.Button("Reset", id="tr-plan-reset", className="plan-btn sm warn",
                            disabled=True),
                html.Button("+ New plan", id="tr-plan-blank", n_clicks=0,
                            className="plan-btn sm")])]),
        html.Div(id="tr-plan-status", className="plan-status"),
    ]),
    # Filing a new plan sits above the list (desk, 2026-10-08); Enter in the box saves.
    html.Div(className="plan-form", children=[
        html.Div(className="plan-row", children=[
            dcc.Input(id="tr-plan-name", type="text", value="",
                      placeholder="new plan name", className="lad-input plan-in"),
            html.Button("Save as new", id="tr-plan-new", n_clicks=0,
                        className="plan-btn")]),
    ]),
    html.Div(className="plan-row plan-subrow", children=[
        html.Div("saved plans", className="card-sub plan-sub"),
        html.Button("Archive plan", id="tr-plan-archive", n_clicks=0,
                    className="plan-btn sm danger")]),
    dcc.RadioItems(id="tr-plan", options=[], value=None, className="plan-list",
                   inputStyle={"display": "none"}),
    html.Div(id="tr-plan-empty", className="plan-empty"),
    html.Div(className="plan-row plan-subrow", children=[
        html.Div("versions — newest first", className="card-sub plan-sub"),
        html.Button("Delete version", id="tr-plan-del", n_clicks=0, disabled=True,
                    className="plan-btn sm danger")]),
    dcc.RadioItems(id="tr-plan-ver", options=[], value=None,
                   className="plan-list plan-vers", inputStyle={"display": "none"}),
    html.Div(id="tr-plan-ver-empty", className="plan-empty"),
    # The note stays under the versions it labels; Save version (top of the Trade panel)
    # reads it, and so does Enter in the box.
    html.Div("note for the next version", className="card-sub plan-sub"),
    html.Div(className="plan-form", children=[
        dcc.Input(id="tr-plan-note", type="text", value="",
                  placeholder="what changed (optional)", className="lad-input plan-in"),
    ]),
])


def _shape_ctl(label: str, cid: str) -> html.Div:
    """A peak's Off · Broad · Medium · Narrow, one segmented control with its label."""
    return html.Div(className="rungs-ctl", children=[
        html.Span(label, className="lad-lbl"),
        dcc.RadioItems(
            id=cid,
            options=[{"label": "Off", "value": "off"},
                     {"label": "Broad", "value": "broad"},
                     {"label": "Medium", "value": "medium"},
                     {"label": "Narrow", "value": "narrow"}],
            value="off", inline=True, inputStyle={"display": "none"},
            className="seg-ctrl"),
    ])


TRADE_PAGE = html.Div(id="trade-wrap", style={"display": "block"}, children=[
    dcc.Store(id="tr-excl-in-store", data={"off": [], "on": []}),
    dcc.Store(id="tr-excl-out-store", data={"off": [], "on": []}),
    dcc.Store(id="tr-held-store", data={}),
    dcc.Store(id="tr-sold-store", data={}),
    dcc.Store(id="tr-depth-store", data=None),
    dcc.Store(id="tr-peak-store", data=None),     # the peak's price, or None
    dcc.Store(id="tr-peak-out-store", data=None), # the way out's peak, or None
    dcc.Store(id="tr-plan-loaded", data=None),    # the saved version the page came from
    dcc.Store(id="tr-plan-msg", data=None),       # the last save / archive message
    dcc.Store(id="tr-plan-del-armed", data=None), # the version a first Delete click armed
    html.Div(className="tr-panels", children=[
    html.Div(className="chart-card panel tr-main", children=[

        html.Div(className="panel-head", children=[
            dcc.RadioItems(
                id="tr-inst", options=list(ladder.DOLLARS_PER_BP), value="SR3",
                inline=True, inputStyle={"display": "none"}, className="seg-ctrl"),
            dcc.RadioItems(
                id="tr-side",
                options=[{"label": "Long", "value": "buy"},
                         {"label": "Short", "value": "sell"}],
                value="buy", inline=True, inputStyle={"display": "none"},
                className="seg-ctrl"),
            # How much ladder is drawn: rungs either side of the market line. Buttons
            # only -- not a field you type in -- and held between 8 and 18. It changes
            # what is on screen, never the sizing.
            dcc.Store(id="tr-rungs", data=TRADE_WINDOW_TICKS),
            html.Div(className="rungs-ctl", children=[
                html.Span("rungs", className="lad-lbl"),
                html.Button("▼", id="tr-rungs-dn", className="theme-btn rungs-btn",
                            title="fewer rungs"),
                html.Span(str(TRADE_WINDOW_TICKS), id="tr-rungs-val",
                          className="rungs-val"),
                html.Button("▲", id="tr-rungs-up", className="theme-btn rungs-btn",
                            title="more rungs"),
            ]),
            # Save version at the end of the first line, over All clear (desk,
            # 2026-10-08). Its label never changes; it is live only with unsaved changes.
            html.Button("Save version", id="tr-plan-save", n_clicks=0, disabled=True,
                        className="plan-btn primary tr-save"),
            html.Div(className="head-break"),
            # The peak's on/off and width in one control (desk, 2026-09-27). Off is the
            # page exactly as before: equal risk, and the dot kept but dimmed. PEAK OUT is
            # the same for the way out (desk, 2026-09-29): Off is equal regret. Both on
            # the second line, with the clear buttons (desk, 2026-10-08).
            _shape_ctl("peak in", "tr-shape"),
            _shape_ctl("peak out", "tr-shape-out"),
            html.Div(className="lad-btns", children=[
                html.Button("Clear skips", id="tr-clear", className="theme-btn"),
                html.Button("Clear filled", id="tr-clear-held", className="theme-btn"),
                html.Button("Clear sold", id="tr-clear-sold", className="theme-btn"),
                html.Button("All clear", id="tr-clear-all",
                            className="theme-btn danger"),
            ]),
        ]),

        html.Div(className="lad-grid", children=[
            html.Div(className="lad-left", children=[
                # The left side is the ladder and nothing else (desk, 2026-09-24): the
                # title sits at the top of the right side.
                html.Div(className="lad-book", children=html.Table(
                    className="lad-table",
                    children=[TRADE_HEAD, html.Tbody(id="tr-rows")])),
                # The how-to line sits under the ladder, not over it (desk, 2026-09-24).
                html.Div("in below the line, out above it - click a size to skip",
                         id="tr-caption", className="card-sub tr-caption"),
            ]),
            html.Div(className="lad-right", children=[
                html.Div(className="card-head", children=[
                    html.Div(id="tr-title", className="card-title"),
                ]),
                _lvl_table("tr", [
                    ("start", _lvl("tr-entry"), _lvl("tr-first")),
                    ("end", _lvl("tr-stop"), _lvl("tr-target")),
                    # Past the stop, the level you are fully out by (desk, 2026-09-30):
                    # the cut runs from one rung past the stop to here. Blank is
                    # everything out at the stop, as before; the note in the cell is
                    # the price the cut averages.
                    ("out by", _lvl("tr-outby"), None),
                    ("average", _avg_cell("tr-avg-in", "in"),
                     _avg_cell("tr-avg-out", "out")),
                    # Blank sizes nothing going in: the empty box says so itself
                    # rather than with a line of its own (desk, 2026-09-25).
                    # ▼ ▲ step it by LOSS_STEP (desk, 2026-09-25), and so do the arrow
                    # keys while the box has the cursor; it stays a box you can type in.
                    ("max loss $", html.Td(className="lvl-cell loss-cell", children=[
                        html.Div(className="loss-step", children=[
                            html.Button("▼", id="tr-loss-dn", n_clicks=0, disabled=True,
                                        className="theme-btn rungs-btn"),
                            html.Button("▲", id="tr-loss-up", n_clicks=0,
                                        className="theme-btn rungs-btn")]),
                        _num("tr-loss", None, ladder.TICK,
                             placeholder="required")]), None),
                    # For the gold-dot row (desk, 2026-09-25): IN is what that depth loses
                    # if stopped, OUT what the way out banks from it -- the LOSS and P&L
                    # of the picked fill-depth row, where the position table used to say it.
                    ("p&l $", _avg_cell("tr-pnl-in", "in"), _avg_cell("tr-pnl-out", "out")),
                    # Where the trade settled (desk, 2026-10-01). The statement marks to
                    # market daily, so it reads as if the book went on at settle; the row
                    # under it is the P&L row again measured from there -- how far the
                    # statement moves. A reference only: nothing is sized on it. The
                    # note in the cell is what the statement already shows.
                    ("settle", _lvl("tr-settle"), None),
                    ("from settle $", _avg_cell("tr-stl-in", "in"),
                     _avg_cell("tr-stl-out", "out")),
                ]),
                # No position table (desk, 2026-09-25): its lots and if-stopped were the
                # picked fill-depth row, its budget the max loss box, its banked the way-out
                # table's "now" row.
                html.Div("if it fills this far, then works out - click a row",
                         className="card-sub lad-depth-head"),
                html.Table(id="tr-depth", className="lad-depth"),
                html.Div(id="tr-exit-head", className="card-sub lad-depth-head"),
                html.Table(id="tr-exit", className="lad-depth"),
                html.Div(id="tr-foot", className="foot"),
            ]),
        ]),
    ]),
    PLANS_PANEL,
    ]),
])


def _in_rule(lp: dict, shape: str) -> str:
    """The way in's sizing rule in words, for the footer."""
    if lp.get("peak") is None:
        return "equal risk in"
    return f"peaked risk in ({lp['peak']:g}, {shape}, half at ±{lp['width']:.2f}bp)"


def _out_rule(ep: dict, shape: str) -> str:
    """The way out's sizing rule in words, for the footer."""
    if ep.get("peak") is None:
        return "equal regret out"
    return f"peaked regret out ({ep['peak']:g}, {shape}, half at ±{ep['width']:.2f}bp)"


# -- Callbacks --------------------------------------------------------------


@callback(
    Output("tr-mark", "placeholder"), Output("tr-caption", "children"),
    Input("tr-side", "value"),
)
def trade_mark_label(side):
    """Long marks to the bid, short to the ask -- the price you could get out at now.
    And the how-to line turns over with the side: a short adds ABOVE the line."""
    if side == "buy":
        return "bid", "in below the line, out above it - click a size to skip"
    return "ask", "in above the line, out below it - click a size to skip"


@callback(
    Output("tr-mark", "value"), Output("tr-entry", "value"),
    Output("tr-stop", "value"), Output("tr-first", "value"),
    Output("tr-target", "value"), Output("tr-loss", "value"),
    Output("tr-outby", "value"), Output("tr-settle", "value"),
    Input("tr-clear-all", "n_clicks"),
    prevent_initial_call=True,
)
def trade_clear_all(_):
    return (None,) * 8


@callback(
    Output("tr-held-store", "data"),
    Input({"type": "tr-held", "p": ALL}, "value"),
    Input("tr-clear-held", "n_clicks"), Input("tr-clear-all", "n_clicks"),
    State({"type": "tr-held", "p": ALL}, "id"),
    State("tr-held-store", "data"),
    prevent_initial_call=True,
)
def trade_collect_held(vals, _clear, _all, ids, cur):
    """What you already hold, per rung -- the same input the scale-in takes."""
    if ctx.triggered_id in ("tr-clear-held", "tr-clear-all"):
        return {}
    out = dict(cur or {})
    for v, i in zip(vals, ids):
        key = str(i["p"])
        if v and int(v) > 0:
            out[key] = int(v)
        else:
            out.pop(key, None)
    if out == (cur or {}):
        raise PreventUpdate
    return out


@callback(
    Output("tr-excl-in-store", "data"),
    Input({"type": "tr-skip-in", "p": ALL}, "n_clicks"),
    Input("tr-clear", "n_clicks"), Input("tr-clear-all", "n_clicks"),
    Input("tr-side", "value"), Input("tr-entry", "value"),
    Input("tr-stop", "value"), Input("tr-mark", "value"),
    State("tr-excl-in-store", "data"),
    State("tr-inst", "value"), State("tr-held-store", "data"),
    State("tr-sold-store", "data"), State("tr-first", "value"),
    State("tr-target", "value"), State("tr-loss", "value"),
    State("tr-excl-out-store", "data"), State("tr-depth-store", "data"),
    State("tr-peak-store", "data"), State("tr-shape", "value"),
    State("tr-outby", "value"),
    prevent_initial_call=True,
)
def trade_skip_in(clicks, _clear, _all, side, entry, stop, mark, store,  # noqa: C901
                  inst, held, sold, first, target, loss, excl_out, depth, peak, shape,
                  out_by=None):
    """Rungs pulled from the way in. Only the rung right above the stop is pulled by
    default here -- the entry rung is worked (desk, 2026-09-24).

    Two stores rather than one, because the two halves can now share a price: the first
    exit is bounded by the average, so a rung you add on may also be one you sell at, and
    a single store keyed by price could not say which of the two you clicked.

    The rungs are worked out exactly as the renderer works them out, and that includes
    the entry standing in as the mark when the box is empty. This used to read the typed
    entry alone, so with the box empty it saw no rungs, no default-pulled ends, and
    treated every click on a default end as a fresh pull -- the end could never come back.
    """
    trig = ctx.triggered_id
    # Snapped to the grid exactly as _trade_setup snaps them, or a typed 20.8 would put
    # the handler's rungs half a tick away from the ones on the page.
    entry = _snap(_fnum(entry))
    if entry is None:
        entry = _snap(_fnum(mark))
    levels = _levels_now(entry, _snap(_fnum(stop)), side)

    if trig == "tr-clear-all":
        return {"off": [], "on": []}
    if trig == "tr-clear":
        return {"off": [], "on": sorted(_trade_default_in_skips(levels))}
    if trig in ("tr-side", "tr-entry", "tr-stop", "tr-mark"):
        return _filter_skips(store, set(levels))

    if not isinstance(trig, dict) or not any(clicks or []):
        raise PreventUpdate

    lv = round(trig["p"] / 2.0, 6)
    store = store or {}
    off = {round(float(x), 6) for x in store.get("off", [])}
    on = {round(float(x), 6) for x in store.get("on", [])}
    # Pulled by default: the rung above the stop, and -- with the peak on -- a rung it
    # sizes to nothing. The second is asked of the plan with no choice of yours on THIS
    # rung, so a click on one reads "put it back", and a second click lets it go again.
    auto = set(_trade_default_in_skips(levels))
    if shape in ladder.PEAK_WIDTHS and peak is not None:
        base = {"off": sorted(off - {lv}), "on": sorted(on - {lv})}
        s = _trade_setup(inst, side, mark, entry, held, sold, stop, first, target, loss,
                         base, excl_out, depth, peak, shape, out_by=out_by)
        if s is not None:
            auto |= s["in_zero"]

    skipped = (lv in auto or lv in off) and lv not in on
    off.discard(lv)
    on.discard(lv)
    if skipped and lv in auto:
        on.add(lv)
    elif not skipped and lv not in auto:
        off.add(lv)
    return {"off": sorted(off), "on": sorted(on)}


@callback(
    Output("tr-sold-store", "data"),
    Input({"type": "tr-sold", "p": ALL}, "value"),
    Input("tr-clear-sold", "n_clicks"), Input("tr-clear-all", "n_clicks"),
    State({"type": "tr-sold", "p": ALL}, "id"),
    State("tr-sold-store", "data"),
    prevent_initial_call=True,
)
def trade_collect_sold(vals, _clear, _all, ids, cur):
    """What you have sold, per rung -- out of what you hold, on the way out."""
    if ctx.triggered_id in ("tr-clear-sold", "tr-clear-all"):
        return {}
    return _gather(vals, ids, cur)


def _trade_setup(inst, side, mark, entry, held_map, sold_map, stop, first, target,
                 max_loss, excl_in, excl_out, depth, peak=None, shape="off",
                 peak_out=None, shape_out="off", out_by=None):
    """The Trade page resolved: both plans for the picked depth, and what each depth banks.

    `peak` (a price) and `shape` (a width mode, or "off") centre the way in's risk on a
    bell curve; see `ladder.peak_weights`. A rung the curve sizes to nothing becomes a
    skip, re-picked every time, unless you put it back. `peak_out` and `shape_out` do the
    same for the way out's regret (`exits.regret_weights`), on every depth's exit.

    `out_by` turns on the cut (desk, 2026-09-30): past the stop, the position comes out
    over the rungs to OUT BY by equal loss (lib/cuts.py), and max loss covers the trade
    all the way there -- the way in is sized to the cut's average, every depth's loss is
    its own book cut through OUT BY, and so is the way out's "if stopped". Blank is the
    page exactly as before.

    Shared by the renderer and the out-skip handler, which must agree on which exit rungs
    exist -- the default-pulled one is derived from them. None until there is a mark.
    """
    mark, entry, stop = _snap(_fnum(mark)), _snap(_fnum(entry)), _snap(_fnum(stop))
    first, target, max_loss = _snap(_fnum(first)), _snap(_fnum(target)), _fnum(max_loss)
    if mark is None:
        return None

    sgn = ladder.sign(side)
    side_word = "long" if side == "buy" else "short"
    problems = []
    sold_note = ""

    # The entry stands in as the mark: until you say otherwise you are getting in where
    # the market is. Everything else is measured off the entry, as on the scale-in.
    if entry is None:
        entry = mark
        problems.append(f"No entry yet, so the ladder is built from the {mark:g} "
                        f"{'bid' if side == 'buy' else 'ask'}.")
    pstop = round(entry - sgn * PROXY_STOP_TICKS * ladder.TICK, 6)
    ptgt = round(entry + sgn * PROXY_TGT_TICKS * ladder.TICK, 6)

    if stop is None:
        stop = pstop
        problems.append(f"No stop yet. Working to {stop:g}.")
    elif sgn * (entry - stop) <= 0:
        bad, stop = stop, pstop
        problems.append(f"A stop at {bad:g} is on the wrong side of a {entry:g} "
                        f"{side_word} — that is not a stop, it is a loss. "
                        f"Showing {stop:g}.")
    if target is None:
        target = ptgt
        problems.append(f"No target yet. Working to {target:g}.")
    elif sgn * (target - entry) <= 0:
        bad, target = target, ptgt
        problems.append(f"A target at {bad:g} is not a profit on a {entry:g} "
                        f"{side_word}. Showing {target:g}.")
    if max_loss is None:
        max_loss = 0.0
        problems.append("No max loss, so the way in is not sized. Say what the trade "
                        "may cost in total.")
    # The cut needs at least one rung past the stop. OUT BY short of that is ignored, not
    # replaced: blank is a real choice here -- everything out at the stop -- so there is
    # no stand-in to show instead.
    out_by_typed = _snap(_fnum(out_by))
    out_by = out_by_typed
    if out_by is not None and sgn * (stop - out_by) < ladder.TICK - 1e-9:
        out_by = None
        problems.append(f"OUT BY at {out_by_typed:g} is not past the {stop:g} stop, so "
                        f"there is nothing to cut between them. Ignoring it.")

    levels_held = _levels_of(held_map)
    sold = _levels_of(sold_map)
    held_n, held_avg = ladder.blend(levels_held)
    n_sold = sum(sold.values())
    if n_sold and not held_n:
        problems.append(f"{n_sold:,} sold, but nothing in Filled — a sale comes out of lots "
                        f"you bought, so type those first. Ignoring the sales until then.")
        sold_note = f"{n_sold:,} sold ignored — nothing in Filled"
        sold, n_sold = {}, 0
    elif n_sold > held_n:
        # Only as many lots can be sold as were filled (desk, 2026-10-04). Which of the
        # sales are real is not known, so the least profitable count first: what is
        # banked can then only be understated, never overstated, and max loss stays a
        # cap. Every figure on the page uses the sales counted; the boxes keep what you
        # typed.
        typed, counted, left = n_sold, {}, held_n
        for p in sorted(sold, key=lambda x: sgn * (x - held_avg)):
            q = min(sold[p], left)
            if q:
                counted[p], left = q, left - q
        sold, n_sold = counted, held_n
        problems.append(f"{typed:,} sold is more than the {held_n:,} filled. Counting "
                        f"{held_n:,}, the least profitable first.")
        sold_note = f"{typed:,} sold is more than the {held_n:,} filled · counting {held_n:,}"
    # Banked against the cost of the lots they came out of, which is the HELD average --
    # not the blended book a depth row describes once the ladder has added to it.
    sold_bp = sum(q * sgn * (p - held_avg) for p, q in sold.items()) if n_sold else 0.0

    # The way in needs no first exit, so it is built first -- and it has to be, because
    # what bounds the first exit is the AVERAGE it produces, not the entry.
    ins = ladder.entry_levels(entry, stop, side)
    in_excl = _trade_effective_in_skips(ins, excl_in or {})

    # The peak, when it is on and sits on a rung you add at. Otherwise flat, and the
    # title says why if a peak was asked for.
    peak_p, peak_note = _snap(_fnum(peak)), ""
    width = ladder.peak_width(shape, entry, stop) if shape in ladder.PEAK_WIDTHS else None
    if width and peak_p is None:
        peak_note = "peak on — click a rung in the dot column"
    elif width and peak_p not in ins:
        peak_note = f"peak at {peak_p:g} is off the way in — sizing flat"
    if not width or peak_p not in ins:
        peak_p, width = None, None

    # The cut's rungs: one past the stop to OUT BY, less any you have already cut through.
    dpb = ladder.DOLLARS_PER_BP[inst]
    cut_ahead = (cuts.ahead_levels(cuts.cut_levels(stop, out_by, side), sold, stop, side)
                 if out_by is not None else [])

    def cut_ref(avg):
        """What a book on at `avg` loses to: the stop, or with a cut, the cut's average."""
        return stop if out_by is None else cuts.reference(avg, cut_ahead, side, out_by)

    def plan_in(excl):
        def at(ref, budget):
            return ladder.plan(entry, stop, target, budget, side, inst, excluded=excl,
                               held_levels=levels_held, sold_lots=n_sold, sold_bp=sold_bp,
                               peak=peak_p, width=width, risk_to=ref)
        if out_by is None:
            return at(None, max_loss)
        # Sized to the cut's average, so the whole book cut through OUT BY fits max loss.
        return cuts.fit_in(at, cut_ahead, side, max_loss, dpb, sold_bp,
                           fallback=out_by, start=stop)[0]

    # Rungs the peak sizes to nothing are skips (desk, 2026-09-27): derived, re-picked
    # each time, never stored -- like the rung above the stop -- and a rung you put back
    # stays in. Each pass gives the rest more, so it settles; nothing is skipped when
    # nothing is sized at all (no max loss, or a filled position using the whole budget).
    lp = plan_in(in_excl)
    in_zero = set()
    if peak_p is not None:
        kept = {round(float(x), 6) for x in (excl_in or {}).get("on", [])}
        for _ in range(len(ins)):
            if sum(lp["plan"]) <= 0:
                break
            zero = {p for p, q in zip(lp["levels"], lp["plan"]) if q == 0} - kept
            if not zero:
                break
            in_zero |= zero
            in_excl = in_excl | zero
            lp = plan_in(in_excl)
    # With a cut, each depth's loss is its own book cut through OUT BY -- the cut's
    # average moves a little with the book's -- and the risk columns on the ladder
    # measure to the full fill's, so their total is the full fill's loss exactly.
    risk_ref = stop
    if out_by is not None:
        cuts.restate(lp["rows"], cut_ahead, side, dpb, out_by, sold_bp)
        full = [r for r in lp["rows"] if r["pos"] > 0]
        risk_ref = cut_ref(full[-1]["avg"]) if full else cut_ref(entry)
    # The join. A scale-in produces a position PER DEPTH, not one position, so the way
    # out is sized for whichever depth is picked -- full fill until you say otherwise.
    depths = [r["depth"] for r in lp["rows"]]
    sel = depth if depth in depths else (depths[-1] if depths else None)
    row = next((x for x in lp["rows"] if x["depth"] == sel), None)

    def book_at(r):
        pos = int(r["pos"]) if r else 0
        return pos, (float(r["avg"]) if r and r["avg"] == r["avg"] else entry)

    def first_for(avg):
        """The first exit for a book on at `avg`: yours if it is a profit on it, else the
        LOWEST profitable rung (highest, on a short) -- the default on this page (desk,
        2026-09-24). A profit on the AVERAGE, not the entry: scaling a long down pulls
        the average below the entry, so the band between them is already money."""
        if first is not None and sgn * (first - avg) > 0:
            return first
        return _first_profit(avg, side)

    pos_d, avg_d = book_at(row)
    pfirst = _first_profit(avg_d, side)
    f_sel = first_for(avg_d)
    if first is None:
        problems.append(f"No first exit yet. Working to {f_sel:g}.")
    elif f_sel != first:
        where = "your average" if pos_d else "the entry"
        problems.append(f"A first exit at {first:g} is not a profit on {where} of "
                        f"{avg_d:.3f}. Showing {f_sel:g}.")
    if sgn * (target - f_sel) < ladder.TICK:
        # No rebuild of the way in: the target only ever priced its P&L column, and that
        # column now comes from the way out below.
        bad, target = target, round(f_sel + sgn * EXIT_SPAN_TICKS * ladder.TICK, 6)
        problems.append(f"A target at {bad:g} leaves no rungs beyond a first exit at "
                        f"{f_sel:g} — it is the boundary you are flat by, not a level "
                        f"you work. Showing {target:g}.")

    basis = held_avg if n_sold else None
    peak_o = _snap(_fnum(peak_out))
    shape_o = shape_out in ladder.PEAK_WIDTHS
    kept_out = {round(float(x), 6) for x in (excl_out or {}).get("on", [])}

    def exit_for(r):
        """The way out for the book one depth row leaves you holding.

        The out peak counts only on a rung still ahead of that book's way out; the width
        is a share of ITS first exit to the target. Rungs the peak sizes to nothing are
        skips, derived as on the way in, and a rung you put back stays in."""
        pos, avg = book_at(r)
        f = first_for(avg)
        ahead = exits.ahead_levels(exits.exit_levels(f, target, side), sold, side)
        skips = _effective_out_skips(ahead, excl_out, _no_default)
        pk = peak_o if shape_o and peak_o in ahead else None
        w = ladder.peak_width(shape_out, f, target) if pk is not None else None

        # The stop side of the way out ("if stopped") is this book cut through OUT BY when
        # there is a cut: its average is where, for its loss, the book is stopped.
        stop_at = cut_ref(avg)

        def plan_out(sk):
            return exits.plan(avg, pos, stop_at, f, target, side, inst, excluded=sk,
                              sold_levels=sold, sold_basis=basis, peak=pk, width=w)

        e, zero = plan_out(skips), set()
        if pk is not None:
            for _ in range(len(ahead)):
                if sum(e["lots"]) <= 0:
                    break
                z = {p for p, q in zip(e["levels"], e["lots"]) if q == 0} - kept_out
                if not z:
                    break
                zero |= z
                skips = skips | z
                e = plan_out(skips)
        return e, skips, zero

    ep, out_excl, out_zero = exit_for(row)
    # The title's word on an out peak that is asked for but not in use.
    peak_out_note = ""
    if shape_o and peak_o is None:
        peak_out_note = "peak out on — click a rung in the blue dot column"
    elif shape_o and ep["peak"] is None:
        peak_out_note = f"peak out at {peak_o:g} is off the way out — equal regret"
    # What every depth BANKS on the way out: that is the depth table's P&L. None where a
    # position has no rung to go to.
    banks = {}
    for r in lp["rows"]:
        e, _, _ = exit_for(r)
        banks[r["depth"]] = (e["rows"][-1]["realised"]
                             if e["levels"] or not r["pos"] else None)

    # The cut for the depth picked -- what goes out at each rung past the stop.
    cp = None
    if out_by is not None:
        cp = cuts.plan(avg_d if pos_d else None, pos_d, stop, out_by, side, inst,
                       sold_levels=sold)
    # When what is already filled loses more than max loss on its own -- at the stop, or
    # cut through OUT BY -- the word for it, with a cut or without one (desk, 2026-10-04):
    # the way in then adds nothing, and nothing it does can bring it back.
    cap_note = ""
    held_row = next((r for r in lp["rows"] if r["held"]), None)
    if held_row is not None and max_loss and held_row["loss"] > max_loss + 0.5:
        where = f"cut to {out_by:g}" if out_by is not None else f"at the {stop:g} stop"
        cap_note = (f"filled loses {_d0(held_row['loss'])} {where}, "
                    f"{_d0(held_row['loss'] - max_loss)} over max loss")

    return {"mark": mark, "entry": entry, "stop": stop, "target": target,
            "first": f_sel, "max_loss": max_loss, "sgn": sgn, "side_word": side_word,
            "problems": problems,
            "ph": (f"{mark:g}", f"{pstop:g}", f"{pfirst:g}", f"{ptgt:g}"),
            "lp": lp, "ep": ep, "depths": depths, "sel": sel, "row": row,
            "pos_d": pos_d, "avg_d": avg_d, "levels_held": levels_held,
            "sold": sold, "n_sold": n_sold, "held_avg": held_avg,
            "sold_note": sold_note, "peak_note": peak_note, "shape": shape,
            "peak_out_note": peak_out_note, "shape_out": shape_out,
            "in_excl": in_excl, "in_zero": in_zero, "out_excl": out_excl,
            "out_zero": out_zero, "banks": banks,
            "out_by": out_by, "out_by_typed": out_by_typed, "cp": cp,
            "risk_ref": risk_ref, "cap_note": cap_note}


@callback(
    Output("tr-excl-out-store", "data"),
    Input({"type": "tr-skip-out", "p": ALL}, "n_clicks"),
    Input("tr-clear", "n_clicks"), Input("tr-clear-all", "n_clicks"),
    Input("tr-side", "value"), Input("tr-first", "value"),
    Input("tr-target", "value"), Input("tr-sold-store", "data"),
    State("tr-inst", "value"), State("tr-mark", "value"), State("tr-entry", "value"),
    State("tr-held-store", "data"), State("tr-stop", "value"), State("tr-loss", "value"),
    State("tr-excl-in-store", "data"), State("tr-depth-store", "data"),
    State("tr-excl-out-store", "data"),
    State("tr-peak-store", "data"), State("tr-shape", "value"),
    State("tr-peak-out-store", "data"), State("tr-shape-out", "value"),
    State("tr-outby", "value"),
    prevent_initial_call=True,
)
def trade_skip_out(clicks, _clear, _all, side, first, target, sold, inst, mark, entry,
                   held, stop, loss, excl_in, depth, store, peak, shape,
                   peak_out=None, shape_out="off", out_by=None):
    """Rungs pulled from the way out. Nothing is pulled by default here (desk,
    2026-09-24) -- except, with the out peak on, a rung it sizes to nothing; a click
    pulls, a click puts back, and moving the rungs filters the store rather than wiping
    it."""
    trig = ctx.triggered_id
    if trig == "tr-clear-all":
        return {"off": [], "on": []}
    s = _trade_setup(inst, side, mark, entry, held, sold, stop, first, target, loss,
                     excl_in, store, depth, peak, shape, peak_out, shape_out, out_by)
    if s is None:
        if trig == "tr-clear":
            return {"off": [], "on": []}
        raise PreventUpdate
    ahead = s["ep"]["ahead"]
    if trig == "tr-clear":
        return {"off": [], "on": sorted(_no_default(ahead))}
    if not isinstance(trig, dict):
        return _filter_skips(store, set(ahead))
    if not any(clicks or []):
        raise PreventUpdate
    lv = round(trig["p"] / 2.0, 6)
    # A rung the out peak sizes to nothing is pulled by default, asked of the plan with
    # no choice of yours on THIS rung -- as on the way in -- so a click on one reads "put
    # it back", and a second click lets it go again.
    auto = set(_no_default(ahead))
    if shape_out in ladder.PEAK_WIDTHS and peak_out is not None:
        st = store or {}
        base = {"off": [x for x in st.get("off", []) if abs(float(x) - lv) > 1e-9],
                "on": [x for x in st.get("on", []) if abs(float(x) - lv) > 1e-9]}
        s0 = _trade_setup(inst, side, mark, entry, held, sold, stop, first, target, loss,
                          excl_in, base, depth, peak, shape, peak_out, shape_out, out_by)
        if s0 is not None:
            auto |= s0["out_zero"]
    return _toggle_skip(store, lv, auto)


@callback(
    Output("tr-peak-store", "data"),
    Input({"type": "tr-peak", "p": ALL}, "n_clicks"),
    Input("tr-clear-all", "n_clicks"),
    State("tr-peak-store", "data"),
    prevent_initial_call=True,
)
def trade_pick_peak(_clicks, _all, cur):
    """The peak: a click on a rung's dot cell puts the gold dot there, a click on the dot
    takes it off. The cells are rebuilt on every change with no clicks, so only a real
    click -- a count above zero on the cell that fired -- counts."""
    return _pick_dot(cur)


def _pick_dot(cur):
    """A click in a dot column: the dot goes where you clicked, or off if it was there."""
    trig = ctx.triggered_id
    if trig == "tr-clear-all":
        return None
    if not isinstance(trig, dict) or not (ctx.triggered and ctx.triggered[0]["value"]):
        raise PreventUpdate
    lv = round(trig["p"] / 2.0, 6)
    return None if cur is not None and abs(float(cur) - lv) < 1e-9 else lv


@callback(
    Output("tr-peak-out-store", "data"),
    Input({"type": "tr-peak-out", "p": ALL}, "n_clicks"),
    Input("tr-clear-all", "n_clicks"),
    State("tr-peak-out-store", "data"),
    prevent_initial_call=True,
)
def trade_pick_peak_out(_clicks, _all, cur):
    """The way out's blue dot, picked exactly as the gold one is."""
    return _pick_dot(cur)


@callback(
    Output("tr-depth-store", "data"),
    Input({"type": "tr-depth", "d": ALL}, "n_clicks"),
    Input("tr-clear-all", "n_clicks"),
    prevent_initial_call=True,
)
def trade_pick_depth(clicks, _all):
    """Which fill depth the way out is sized for. None means the full fill."""
    trig = ctx.triggered_id
    if trig == "tr-clear-all":
        return None
    if not isinstance(trig, dict) or not any(clicks or []):
        raise PreventUpdate
    return trig["d"]


# The rungs counter runs in the browser, not on the server. Server-side, two quick clicks
# could both read the same count before the store updated, and one was lost; clientside
# every click lands. One rung more or fewer either side of the line, held between the
# limits, and the button greys out at each end rather than silently doing nothing.
clientside_callback(
    f"""
    function(dn, up, cur) {{
        const t = (dash_clientside.callback_context.triggered[0] || {{}}).prop_id || "";
        let n = cur || {TRADE_WINDOW_TICKS};
        if (t.startsWith("tr-rungs-dn")) n -= 1;
        else if (t.startsWith("tr-rungs-up")) n += 1;
        return Math.max({TRADE_RUNGS_MIN}, Math.min({TRADE_RUNGS_MAX}, n));
    }}
    """,
    Output("tr-rungs", "data"),
    Input("tr-rungs-dn", "n_clicks"), Input("tr-rungs-up", "n_clicks"),
    State("tr-rungs", "data"),
    prevent_initial_call=True,
)
# Max loss steps by LOSS_STEP from its ▼ ▲ and the arrow keys. The stepping itself is in
# assets/trade-loss.js, which writes the box the way typing does: a callback writing the
# value lost quick clicks (Dash folds them into one) and was then overwritten by the
# box's own half-second debounce if you had typed a moment before. Written as typing, it
# re-arms that debounce, so a run of clicks re-sizes once, when you stop. Only the greyed
# ▼ at the floor is a callback, and it follows the committed value.
LOSS_STEP = 500     # also in assets/trade-loss.js
clientside_callback(
    f"""
    function(v) {{
        const n = Number(String(v || "").replace(/[,$\s]/g, ""));
        return !(n > {LOSS_STEP});
    }}
    """,
    Output("tr-loss-dn", "disabled"),
    Input("tr-loss", "value"),
)
# The number and the greyed ends follow the STORE, not the clicks, so a loaded plan's
# rungs count shows as well as draws.
clientside_callback(
    f"""
    function(n) {{
        n = n || {TRADE_WINDOW_TICKS};
        return [String(n), n <= {TRADE_RUNGS_MIN}, n >= {TRADE_RUNGS_MAX}];
    }}
    """,
    Output("tr-rungs-val", "children"),
    Output("tr-rungs-dn", "disabled"), Output("tr-rungs-up", "disabled"),
    Input("tr-rungs", "data"),
)


@callback(
    Output("tr-rows", "children"), Output("tr-title", "children"),
    Output("tr-depth", "children"),
    Output("tr-exit-head", "children"), Output("tr-exit", "children"),
    Output("tr-foot", "children"),
    Output("tr-entry", "placeholder"), Output("tr-stop", "placeholder"),
    Output("tr-first", "placeholder"), Output("tr-target", "placeholder"),
    Output("tr-entry-use", "children"), Output("tr-stop-use", "children"),
    Output("tr-first-use", "children"), Output("tr-target-use", "children"),
    Output("tr-avg-in", "children"), Output("tr-avg-out", "children"),
    Output("tr-pnl-in", "children"), Output("tr-pnl-out", "children"),
    Output("tr-outby", "placeholder"), Output("tr-outby-use", "children"),
    Output("tr-settle", "placeholder"), Output("tr-settle-use", "children"),
    Output("tr-stl-in", "children"), Output("tr-stl-out", "children"),
    Input("tr-inst", "value"), Input("tr-side", "value"),
    Input("tr-mark", "value"), Input("tr-entry", "value"),
    Input("tr-held-store", "data"), Input("tr-sold-store", "data"),
    Input("tr-stop", "value"), Input("tr-first", "value"),
    Input("tr-target", "value"), Input("tr-loss", "value"),
    Input("tr-excl-in-store", "data"), Input("tr-excl-out-store", "data"),
    Input("tr-depth-store", "data"), Input("tr-rungs", "data"),
    Input("tr-peak-store", "data"), Input("tr-shape", "value"),
    Input("tr-peak-out-store", "data"), Input("tr-shape-out", "value"),
    Input("tr-outby", "value"), Input("tr-settle", "value"),
)
def draw_trade(inst, side, mark, entry, held_map, sold_map, stop, first, target,
               max_loss, excl_in, excl_out, depth, rungs=TRADE_WINDOW_TICKS,
               peak=None, shape="off", peak_out=None, shape_out="off", out_by=None,
               settle=None):
    """One trade, both halves, no flipping -- and, with OUT BY, the cut past the stop.

    The mark loads the ladder. Everything else is optional and
    lands on rungs that are already there, and the ladder stays on screen whatever is
    wrong with the numbers -- it is how you see what is wrong.
    """
    s = _trade_setup(inst, side, mark, entry, held_map, sold_map, stop, first, target,
                     max_loss, excl_in, excl_out, depth, peak, shape, peak_out, shape_out,
                     out_by)
    if s is None:
        lbl = "bid" if side == "buy" else "ask"
        return ([], "", [], f"type the {lbl} at the top of the ladder", [],
                "", "entry", "stop", "first", "target", "", "", "", "", "—", "—", "—", "—",
                "at stop", "", "none", "", "—", "—")

    # Inside OUT BY's cell: the price the cut averages for the depth picked -- where, for
    # its loss, the book is really stopped -- or why a typed OUT BY is not in use. Blank
    # needs no note: the placeholder says everything goes out at the stop.
    cp = s["cp"]
    if s["out_by_typed"] is not None and s["out_by"] is None:
        ob_note = "not past the stop · ignored"
    else:
        bits = [_use_text(out_by, s["out_by"]) if s["out_by"] is not None else ""]
        if cp and cp["avg_cut"] is not None:
            bits.append(f"avg cut {cp['avg_cut']:.3f}")
        ob_note = " · ".join(b for b in bits if b)
    ob = ("at stop", ob_note)

    # Under each box: the value in use when it is not what you typed -- so this reads the
    # typed values before they are replaced below -- and the two averages.
    extra = [_use_text(t, u) for t, u in
             zip((entry, stop, first, target),
                 (s["entry"], s["stop"], s["first"], s["target"]))] + ["—", "—"]
    typed_first = _snap(_fnum(first))

    mark, entry, stop, target = s["mark"], s["entry"], s["stop"], s["target"]
    first, max_loss, sgn = s["first"], s["max_loss"], s["sgn"]
    lp, ep, depths, sel, row = s["lp"], s["ep"], s["depths"], s["sel"], s["row"]
    pos_d, avg_d, n_sold = s["pos_d"], s["avg_d"], s["n_sold"]
    side_word, ph = s["side_word"], s["ph"]

    # Inside the first exit's cell, always: the limit on 1ST -- the first rung that is a
    # profit on the average for the depth picked, "min" on a long, "max" on a short
    # (desk, 2026-09-25; it read "lowest profitable 21"). When a typed 1ST is past the
    # limit it is replaced by the limit and the note says so; when it only needed
    # snapping to the grid the note says what it snapped to, then the limit.
    lowest = _first_profit(avg_d, side)
    lim = "min" if side == "buy" else "max"
    if extra[2]:
        past = typed_first is not None and sgn * (typed_first - lowest) < -1e-9
        on_lim = typed_first is not None and abs(typed_first - lowest) < 1e-9
        extra[2] = (f"{'below' if side == 'buy' else 'above'} {lim} · using {lowest:g}"
                    if past else f"{extra[2]} · {lim}" if on_lim   # snapped onto it
                    else f"{extra[2]} · {lim} {lowest:g}")
    else:
        extra[2] = f"{lim} {lowest:g}"

    if pos_d:
        extra[4] = f"{avg_d:.3f}"
        if ep["avg_out"] == ep["avg_out"]:
            extra[5] = f"{ep['avg_out']:.3f}"
    ticks = max(TRADE_RUNGS_MIN, min(TRADE_RUNGS_MAX, int(rungs or TRADE_WINDOW_TICKS)))
    book = _trade_book(lp, ep, side, mark, avg_d if pos_d else None,
                       held_map, sold_map, s["in_excl"], s["out_excl"], ticks, sel,
                       peak=_snap(_fnum(peak)), shape_on=shape in ladder.PEAK_WIDTHS,
                       peak_out=_snap(_fnum(peak_out)),
                       shape_out_on=shape_out in ladder.PEAK_WIDTHS,
                       cp=cp, risk_ref=s["risk_ref"])

    title = (f"{inst}   {side_word}   {entry:g} → {stop:g} in, "
             f"{first:g} → {target:g} out")
    if cp:
        title += f", {cp['all_levels'][0]:g} → {cp['all_levels'][-1]:g} cut"
    if s["cap_note"]:
        title += f"   ·   {s['cap_note']}"
    if lp["held"]:
        title += f"   ·   {lp['held']:,} already on at {lp['held_avg']:.3f}"
    if s["peak_note"]:
        title += f"   ·   {s['peak_note']}"
    if s["peak_out_note"]:
        title += f"   ·   {s['peak_out_note']}"
    if s["sold_note"]:                 # says the count itself, so not both
        title += f"   ·   {s['sold_note']}"
    elif n_sold:
        title += f"   ·   {n_sold:,} sold"

    # The P&L row: the gold-dot row's loss if stopped, and what its way out banks.
    pnl = s["banks"].get(sel) if row else None
    have_pnl = pnl is not None and pnl == pnl
    extra += [_d0(-row["loss"]) if row else "—", _d0(pnl) if have_pnl else "—"]

    # From settle: the same two figures less what the statement already shows. The cell
    # note says what that is, or that nothing is on yet, when the two rows agree.
    settle_px = _fnum(settle)
    marked = _settle_marked(lp, settle_px, sgn)
    if marked is None:
        stl = ("none", "", "—", "—")
    else:
        note = (f"on books {_d0(marked)}" if lp["held"] or lp["sold"]
                else "nothing on yet · same as p&l")
        stl = ("none", note, _d0(-row["loss"] - marked) if row else "—",
               _d0(pnl - marked) if have_pnl else "—")

    if not lp["levels"] and not ep["levels"]:
        return (book, title, [], "no rungs between the stop and the target", [],
                "", *ph, *extra, *ob, *stl)

    depth_tbl = _trade_depth_rows(lp, sel, s["banks"])
    if pos_d:
        head = (f"then, coming out of {pos_d:,}"
                + (" still on" if n_sold else "") + f" at {avg_d:.3f}"
                + f" — {_depth_label(sel, depths, bool(lp['held']))}")
    else:
        head = "then, coming out — nothing to sell yet"
    exit_tbl = _exit_rows(ep, "if cut" if cp else "if stopped")

    # With a cut, the way in's risk is measured to the cut's average, and the footer says
    # to what: the one number that explains why the way in got smaller.
    cut_rule = (f", equal loss cut, risk in measured to its {s['risk_ref']:.3f} average"
                if cp else "")
    foot = (f"{inst}  ·  ${lp['dollars_per_bp']:,.2f}/bp  ·  "
            f"${lp['tick_value']:,.2f}/tick  ·  {ladder.TICK}bp grid  ·  "
            f"{_in_rule(lp, shape)}, {_out_rule(ep, shape_out)}{cut_rule}  ·  stop "
            f"excluded going in{' and cutting' if cp else ''}, target "
            f"excluded coming out  ·  no flipping on this page")

    return (book, title, depth_tbl, head, exit_tbl, foot, *ph, *extra, *ob, *stl)





# -- Saved plans (Trade) ------------------------------------------------------
# lib/plans.py keeps the files; this is the page's side of it. A plan is every input on
# the Trade page, so these are the fields a save reads and a load writes back.

PLANS_DIR = ROOT / "plans"

# The board is open to the office network (desk, 2026-10-07) and the Risk book is filled
# from these files, so only the PC the board runs on can change them. Anyone else can load
# a plan and work the page; Save version, Save as new, Archive and Delete refuse.
_HOST_ADDRS = {"127.0.0.1", "::1"}
try:
    _HOST_ADDRS |= set(socket.gethostbyname_ex(socket.gethostname())[2])
except OSError:
    pass
_HOST_ONLY = "Plans are saved, archived and deleted on the board's own PC only."


def _on_host() -> bool:
    """Is this click from the PC the board runs on -- loopback or one of its own addresses?
    A call with no request behind it (a test, a script) is on this PC by definition."""
    return not has_request_context() or request.remote_addr in _HOST_ADDRS


_PLAN_TEXT =("mark", "entry", "stop", "first", "target", "loss", "outby", "settle")
PLAN_FIELDS = [
    ("inst", "tr-inst", "value"), ("side", "tr-side", "value"),
    ("mark", "tr-mark", "value"), ("entry", "tr-entry", "value"),
    ("stop", "tr-stop", "value"), ("first", "tr-first", "value"),
    ("target", "tr-target", "value"), ("loss", "tr-loss", "value"),
    # Plans saved before the cut have no OUT BY: they load with it blank, exactly as they
    # were, and do not read as changed.
    ("outby", "tr-outby", "value"),
    # Plans saved before the settle have none: they load with it blank, unchanged.
    ("settle", "tr-settle", "value"),
    ("held", "tr-held-store", "data"), ("sold", "tr-sold-store", "data"),
    ("excl_in", "tr-excl-in-store", "data"), ("excl_out", "tr-excl-out-store", "data"),
    ("depth", "tr-depth-store", "data"), ("rungs", "tr-rungs", "data"),
    ("peak", "tr-peak-store", "data"), ("shape", "tr-shape", "value"),
    ("peak_out", "tr-peak-out-store", "data"), ("shape_out", "tr-shape-out", "value"),
]
_PLAN_STATES = [State(cid, prop) for _, cid, prop in PLAN_FIELDS]
_PLAN_INPUTS = [Input(cid, prop) for _, cid, prop in PLAN_FIELDS]


def _plan_norm(st) -> dict | None:
    """One canonical form for a plan's inputs, so "is the page what I saved?" is a plain
    comparison: blank text is None, empty maps are {}, skip lists are sorted."""
    if not st:
        return None
    out = {}
    for k, _, _ in PLAN_FIELDS:
        v = st.get(k)
        if k in _PLAN_TEXT:
            v = (str(v).strip() or None) if v is not None else None
        elif k in ("held", "sold"):
            v = {str(a): int(b) for a, b in (v or {}).items() if b}
        elif k in ("excl_in", "excl_out"):
            v = v or {}
            v = {"off": sorted(round(float(x), 6) for x in v.get("off", [])),
                 "on": sorted(round(float(x), 6) for x in v.get("on", []))}
        elif k == "rungs":
            v = int(v or TRADE_WINDOW_TICKS)
        elif k in ("peak", "peak_out"):  # plans saved before a peak have none: flat
            v = round(float(v), 6) if v is not None else None
        elif k in ("shape", "shape_out"):
            v = v if v in ladder.PEAK_WIDTHS else "off"
        out[k] = v
    return out


def _plan_state(vals) -> dict:
    return _plan_norm({k: v for (k, _, _), v in zip(PLAN_FIELDS, vals)})


def _plan_snapshot(st: dict) -> dict:
    """What the page SAID with these inputs, kept beside them so a later version can be
    read against this one even after the sizing rules change."""
    s = _trade_setup(st["inst"], st["side"], st["mark"], st["entry"], st["held"],
                     st["sold"], st["stop"], st["first"], st["target"], st["loss"],
                     st["excl_in"], st["excl_out"], st["depth"], st["peak"], st["shape"],
                     st["peak_out"], st["shape_out"], st.get("outby"))
    if s is None:
        return {}
    lp, ep, row, cp = s["lp"], s["ep"], s["row"], s["cp"]
    live = bool(s["pos_d"])
    pnl = s["banks"].get(s["sel"]) if row else None
    snap = {
        "entry": s["entry"], "stop": s["stop"], "first": s["first"],
        "target": s["target"], "max_loss": s["max_loss"],
        "depth": _depth_label(s["sel"], s["depths"], bool(lp["held"])),
        "position": s["pos_d"],
        "avg_in": round(s["avg_d"], 4) if live else None,
        "avg_out": (round(ep["avg_out"], 4)
                    if live and ep["avg_out"] == ep["avg_out"] else None),
        "if_stopped": round(-row["loss"], 2) if row else None,
        "pnl": round(pnl, 2) if pnl is not None else None,
        "in": {f"{p:g}": q for p, q in zip(lp["levels"], lp["lots"]) if q},
        "out": {f"{p:g}": q for p, q in zip(ep["levels"], ep["lots"]) if q},
    }
    marked = _settle_marked(lp, _fnum(st.get("settle")), s["sgn"])
    if marked is not None:      # a reference only: what the statement already shows
        snap.update({"settle": _fnum(st.get("settle")), "on_books": round(marked, 2)})
    if cp:          # with a cut, "if_stopped" above is the loss cut through OUT BY
        snap.update({
            "out_by": s["out_by"],
            "avg_cut": round(cp["avg_cut"], 4) if cp["avg_cut"] is not None else None,
            "cut": {f"{p:g}": q for p, q in zip(cp["levels"], cp["lots"]) if q}})
    return snap


def _plan_when(iso) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _plan_ver_label(v: dict) -> str:
    """v3 · 24 Sep 17:40 · 144 lots, out 22.656 · moved stop after CPI"""
    snap = v.get("snapshot") or {}
    bits = [f"v{v['n']}", _plan_when(v.get("saved_at"))]
    if snap.get("position"):
        bits.append(f"{snap['position']:,} lots"
                    + (f", out {snap['avg_out']:.3f}" if snap.get("avg_out") else ""))
    if v.get("note"):
        bits.append(v["note"])
    return " · ".join(bits)


_NL = chr(10)      # the line break inside a two-line list label


def _plan_ver_item(v: dict) -> str:
    """One row per version, two lines: "v3 · 24 Sep 17:40", then what it said and why.

    Plain text with a line break, not components: Dash's radio list errors when its
    option labels are components and the list grows, and quietly keeps the old list --
    a save then never showed up. CSS bolds the first line."""
    snap = v.get("snapshot") or {}
    what = []
    if snap.get("position"):
        what.append(f"{snap['position']:,} lots"
                    + (f", out {snap['avg_out']:.3f}" if snap.get("avg_out") else ""))
    if v.get("note"):
        what.append(v["note"])
    return (f"v{v['n']} · {_plan_when(v.get('saved_at'))}" + _NL
            + (" · ".join(what) or "—"))


def _plan_options() -> list:
    """One row per plan, two lines: its name, then how many versions and when it moved."""
    return [{"label": pl["name"] + _NL + f"{pl['versions']} version"
                      f"{'s' if pl['versions'] != 1 else ''} · "
                      f"{_plan_when(pl['updated'])}",
             "value": pl["name"]}
            for pl in plans.list_plans(PLANS_DIR)]


def _plan_versions(name) -> tuple:
    """Version options for a plan, newest first, and the value of the newest."""
    data = plans.load(PLANS_DIR, name) if name else None
    if not data or not data.get("versions"):
        return [], None
    vs = data["versions"]
    opts = [{"label": _plan_ver_item(v), "value": f"{data['name']}::{v['n']}"}
            for v in reversed(vs)]
    return opts, f"{data['name']}::{vs[-1]['n']}"


def _plan_msg(text: str, vals) -> dict:
    """A message for the status line, tied to the page as it was when it was said, so it
    clears itself the moment you change anything instead of sticking there for good."""
    return {"text": text, "state": _plan_state(vals)}


def _plan_loaded(data: dict, v: dict) -> dict:
    return {"plan": data["name"], "n": v["n"], "saved_at": v["saved_at"],
            "state": _plan_norm(v["state"])}


@callback(
    Output("tr-plan", "options"),
    Input("page", "value"),
)
def plan_list(_page):
    """The plan list is read from disk whenever the page switcher moves, so a plan saved
    in another tab, or before a restart, is there."""
    return _plan_options()


@callback(
    Output("tr-plan-empty", "children"), Output("tr-plan-ver-empty", "children"),
    Input("tr-plan", "options"), Input("tr-plan-ver", "options"),
)
def plan_empty(p_opts, v_opts):
    """Say so when a list is empty, rather than leave a gap that looks broken."""
    return ("" if p_opts else "no saved plans yet — name one above",
            "" if v_opts else "pick a plan to see its versions")


@callback(
    Output("tr-plan-ver", "options"), Output("tr-plan-ver", "value"),
    Input("tr-plan", "value"),
)
def plan_versions(name):
    """Picking a plan lists its versions and selects the newest -- which loads it."""
    return _plan_versions(name)


@callback(
    *[Output(cid, prop, allow_duplicate=True) for _, cid, prop in PLAN_FIELDS],
    Output("tr-plan-loaded", "data"),
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Input("tr-plan-ver", "value"),
    State("tr-plan-loaded", "data"),
    prevent_initial_call=True,
)
def plan_load(ver, loaded):
    """Put a saved version back on the page: every field and every store. Skipped when
    the version is the one the page already holds -- which is what a save just made."""
    if not ver or "::" not in ver:
        raise PreventUpdate
    name, n = ver.rsplit("::", 1)
    data = plans.load(PLANS_DIR, name)
    v = next((x for x in (data or {}).get("versions", []) if str(x["n"]) == n), None)
    if v is None:
        raise PreventUpdate
    st = _plan_norm(v["state"])
    if (loaded and loaded.get("plan") == data["name"] and loaded.get("n") == v["n"]
            and loaded.get("state") == st):
        raise PreventUpdate
    return (*[st[k] for k, _, _ in PLAN_FIELDS], _plan_loaded(data, v), None)


@callback(
    Output("tr-plan", "options", allow_duplicate=True),
    Output("tr-plan-ver", "options", allow_duplicate=True),
    Output("tr-plan-ver", "value", allow_duplicate=True),
    Output("tr-plan-loaded", "data", allow_duplicate=True),
    Output("tr-plan-note", "value"),
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Input("tr-plan-save", "n_clicks"), Input("tr-plan-note", "n_submit"),
    State("tr-plan", "value"), State("tr-plan-note", "value"),
    State("tr-plan-loaded", "data"),
    *_PLAN_STATES,
    prevent_initial_call=True,
)
def plan_save(_n, _enter, name, note, loaded, *vals):
    """A new version of the loaded plan. Never overwrites the one before.

    Enter in the note box is the button (desk, 2026-10-08), so it does nothing when the
    button is grey: with no unsaved changes a save would only copy the version you are on."""
    if (ctx.triggered_id == "tr-plan-note"
            and not (loaded and _plan_state(vals) != loaded.get("state"))):
        raise PreventUpdate
    if not _on_host():
        return (no_update,) * 5 + (_plan_msg(_HOST_ONLY, vals),)
    if not name:
        return (no_update,) * 5 + (_plan_msg(
            "Pick a plan to save a version of, or name one and Save as new plan.", vals),)
    st = _plan_state(vals)
    try:
        data = plans.save_version(PLANS_DIR, name, st, _plan_snapshot(st), note or "")
    except FileNotFoundError:
        return (_plan_options(),) + (no_update,) * 4 + (_plan_msg(
            f"“{name}” is no longer in plans/ — Save as new plan to keep this.",
            vals),)
    opts, value = _plan_versions(data["name"])
    return (_plan_options(), opts, value, _plan_loaded(data, data["versions"][-1]),
            "", None)


@callback(
    Output("tr-plan", "options", allow_duplicate=True),
    Output("tr-plan", "value"),
    Output("tr-plan-loaded", "data", allow_duplicate=True),
    Output("tr-plan-name", "value"),
    Output("tr-plan-note", "value", allow_duplicate=True),
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Input("tr-plan-new", "n_clicks"), Input("tr-plan-name", "n_submit"),
    State("tr-plan-name", "value"), State("tr-plan-note", "value"),
    *_PLAN_STATES,
    prevent_initial_call=True,
)
def plan_save_new(_n, _enter, name, note, *vals):
    """File the page as a new plan -- a new trade, or a different scenario of one. Enter
    in the name box is the button (desk, 2026-10-08)."""
    if not _on_host():
        return (no_update,) * 5 + (_plan_msg(_HOST_ONLY, vals),)
    name = (name or "").strip()
    if not plans.slug(name):
        return (no_update,) * 5 + (_plan_msg("Type a name for the new plan first.",
                                             vals),)
    if plans.exists(PLANS_DIR, name):
        return (no_update,) * 5 + (_plan_msg(
            f"There is already a plan called “{name}”. Pick it and Save version, or "
            f"choose another name.", vals),)
    st = _plan_state(vals)
    data = plans.create(PLANS_DIR, name, st, _plan_snapshot(st), note or "")
    return (_plan_options(), data["name"], _plan_loaded(data, data["versions"][-1]),
            "", "", None)


@callback(
    Output("tr-plan", "options", allow_duplicate=True),
    Output("tr-plan", "value", allow_duplicate=True),
    Output("tr-plan-loaded", "data", allow_duplicate=True),
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Input("tr-plan-archive", "n_clicks"),
    State("tr-plan", "value"),
    *_PLAN_STATES,
    prevent_initial_call=True,
)
def plan_archive(_n, name, *vals):
    """Take a plan off the list. The file moves to plans/_archive/ -- nothing is erased,
    and moving it back restores it. The page keeps what is on it."""
    if not _on_host():
        return no_update, no_update, no_update, _plan_msg(_HOST_ONLY, vals)
    if not name:
        return no_update, no_update, no_update, _plan_msg("No plan loaded to archive.",
                                                          vals)
    plans.archive(PLANS_DIR, name)
    return (_plan_options(), None, None, _plan_msg(
        f"Archived “{name}” — the file is in plans/_archive/.", vals))


@callback(
    *[Output(cid, prop, allow_duplicate=True) for _, cid, prop in PLAN_FIELDS],
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Input("tr-plan-reset", "n_clicks"),
    State("tr-plan-loaded", "data"),
    prevent_initial_call=True,
)
def plan_reset(_n, loaded):
    """Throw away every change since the loaded version: each field and store goes back
    to what that version saved. Nothing on disk changes."""
    st = (loaded or {}).get("state")
    if not st:
        raise PreventUpdate
    return (*[st[k] for k, _, _ in PLAN_FIELDS], None)


_PLAN_BLANK = {"mark": None, "entry": None, "stop": None, "first": None,
               "target": None, "loss": None, "outby": None, "settle": None,
               "held": {}, "sold": {},
               "excl_in": {"off": [], "on": []}, "excl_out": {"off": [], "on": []},
               "depth": None, "rungs": TRADE_WINDOW_TICKS, "peak": None, "shape": "off",
               "peak_out": None, "shape_out": "off"}


@callback(
    *[Output(cid, prop, allow_duplicate=True) for _, cid, prop in PLAN_FIELDS],
    Output("tr-plan", "value", allow_duplicate=True),
    Output("tr-plan-loaded", "data", allow_duplicate=True),
    Output("tr-plan-msg", "data", allow_duplicate=True),
    Output("tr-plan-name", "value", allow_duplicate=True),
    Output("tr-plan-note", "value", allow_duplicate=True),
    Input("tr-plan-blank", "n_clicks"),
    State("tr-inst", "value"), State("tr-side", "value"),
    prevent_initial_call=True,
)
def plan_blank(_n, inst, side):
    """Start a new plan: a blank page -- every level, Held, Sold, skip and depth cleared,
    rungs back to the default -- tied to no saved plan, ready to be named and saved as
    new. The instrument and side stay as they were. Saved plans are untouched."""
    st = dict(_PLAN_BLANK, inst=inst, side=side)
    return (*[st[k] for k, _, _ in PLAN_FIELDS], None, None, None, "", "")


@callback(
    Output("tr-plan-del", "children"), Output("tr-plan-del", "disabled"),
    Output("tr-plan-del", "className"), Output("tr-plan-del", "title"),
    Input("tr-plan-ver", "value"), Input("tr-plan-ver", "options"),
    Input("tr-plan-del-armed", "data"),
)
def plan_del_label(ver, opts, armed):
    """Delete names the version it would take, and asks for a second click before it
    does. A plan's only version cannot go -- archive the plan instead. Off the board's own
    PC it never goes live."""
    if not ver or "::" not in ver:
        return "Delete version", True, "plan-btn sm danger", ""
    n = ver.rsplit("::", 1)[1]
    if not _on_host():
        return f"Delete v{n}", True, "plan-btn sm danger", "on the board's own PC only"
    if len(opts or []) <= 1:
        return (f"Delete v{n}", True, "plan-btn sm danger",
                "its only version — archive the plan instead")
    if armed == ver:
        return f"Confirm delete v{n}", False, "plan-btn sm danger armed", ""
    return f"Delete v{n}", False, "plan-btn sm danger", ""


@callback(
    Output("tr-plan-del-armed", "data"),
    Output("tr-plan-ver", "options", allow_duplicate=True),
    Output("tr-plan-ver", "value", allow_duplicate=True),
    Output("tr-plan", "options", allow_duplicate=True),
    Input("tr-plan-del", "n_clicks"),
    State("tr-plan-ver", "value"), State("tr-plan-del-armed", "data"),
    prevent_initial_call=True,
)
def plan_delete(_n, ver, armed):
    """First click arms, second deletes. The version is written to plans/_archive/ before
    it leaves the plan (lib/plans.py), and the newest version left is then loaded."""
    if not _on_host() or not ver or "::" not in ver:
        raise PreventUpdate
    if armed != ver:
        return ver, no_update, no_update, no_update
    name, n = ver.rsplit("::", 1)
    try:
        data = plans.delete_version(PLANS_DIR, name, int(n))
    except (FileNotFoundError, KeyError, ValueError):
        return None, no_update, no_update, _plan_options()
    opts, value = _plan_versions(data["name"])
    return None, opts, value, _plan_options()


@callback(
    Output("tr-plan-status", "children"),
    Output("tr-plan-reset", "children"), Output("tr-plan-reset", "disabled"),
    Output("tr-plan-save", "disabled"),
    Input("tr-plan-loaded", "data"), Input("tr-plan-msg", "data"),
    *_PLAN_INPUTS,
)
def plan_status(loaded, msg, *vals):
    """One line under the plan bar: the last message, else where the page stands against
    the version it came from -- with a dot when it has moved on since. Reset and Save
    version are live only then: with nothing changed there is nothing to undo, and a
    save would only copy the version you are on."""
    now = _plan_state(vals)
    dirty = bool(loaded) and now != loaded.get("state")
    reset = (f"Reset to v{loaded['n']}" if loaded else "Reset", not dirty, not dirty)
    # A message shows only while the page is as it was when the message was written;
    # change anything and it gives way to the normal status.
    if isinstance(msg, dict) and msg.get("state") == now:
        return html.Span(msg.get("text", ""), className="plan-msg"), *reset
    if not loaded:
        return html.Span("not saved — name it above and Save as new",
                         className="plan-quiet"), *reset
    when = _plan_when(loaded.get("saved_at"))
    if dirty:
        return html.Span(f"● unsaved changes since v{loaded['n']} ({when})",
                         className="plan-dirty"), *reset
    mark = "bid" if (loaded.get("state") or {}).get("side", "buy") == "buy" else "ask"
    return html.Span(f"v{loaded['n']} · saved {when} · the {mark} is as it was then",
                     className="plan-quiet"), *reset
