"""
The cut: working out of a trade that has gone through its stop, over the rungs past it.

The stop on the Trade page is the level the trade most likely will not go beyond (desk,
2026-09-30) -- the place the way in stops adding -- and no longer the one price every lot
is thrown out at. If it does go beyond, the position comes out over the rungs from one
past the stop to OUT BY, the level you are fully out by, because only so much P&L can be
given to one trade. This module sizes that.

A partition, like the way out
-----------------------------
By the time the stop breaks, the size is settled: whatever the way in built. So the lots
cut across the rungs add up to the position exactly, which is the way out's constraint
rather than the way in's. Anything left over would be a lot you forgot to cut.

The rule: equal loss
--------------------
Every rung past the stop takes the same dollars of loss, the way every rung going in puts
the same dollars at risk. A lot cut at `x` loses ``sgn * (avg - x)``, so

    q  proportional to  1 / |avg - x|

and the lots taper as you go deeper, because a lot cut deeper loses more. Nothing is
degenerate here: the average is never on the band, so no rung would take unbounded size.
Both ends are rungs. The stop is not one -- it is the level the trade should hold, and the
cut starts once it trades through -- and OUT BY is, being where the last lots go.

It is measured from the AVERAGE, so the split moves a little with the fill depth: a
shallow book sits further above the band and splits flatter. Each depth gets its own.

For sizing, a stop at its average
---------------------------------
Cut through every rung, a book of `n` lots at `avg` loses ``n * sgn * (avg - c)``, where
`c` is the cut's average price -- exactly what one stop at `c` would lose. So the way in
is sized to it: equal risk measured to the cut's average rather than to the stop
(`ladder.plan`'s `risk_to`), which puts max loss over the whole trade, OUT BY included.
Holding lots past the stop is paid for with lots on the way in. `fit_in` does this.

Rounding never breaks the cap
-----------------------------
Lots are floored and the remainder goes to the rungs NEAREST the stop, one each -- not to
the largest fractions, as on the way out. That keeps the whole lots' loss at or under the
unrounded split's, so the cap the way in was sized to still holds once the lots are whole.
The unrounded figure is the one every table reports: it is the bound.

What you have already cut
-------------------------
A cut is typed in `Sold`, as any sale is. What is still on is split across the rungs
beyond the furthest cut, the way the way out passes the rungs behind its furthest sale.
"""

from __future__ import annotations

from ladder import DOLLARS_PER_BP, TICK, sign          # noqa: F401  (re-exported)


def cut_levels(stop: float, out_by: float, side: str, tick: float = TICK) -> list[float]:
    """The rungs you cut at: one past the stop, through `out_by` itself.

    Empty unless OUT BY is at least a rung beyond the stop -- below it on a long, above it
    on a short.
    """
    sgn = sign(side)
    steps = int(round(sgn * (stop - out_by) / tick))
    if steps < 1:
        return []
    return [round(stop - sgn * i * tick, 6) for i in range(1, steps + 1)]


def ahead_levels(levels: list[float], sold_levels, stop: float, side: str) -> list[float]:
    """The cut rungs still in front of you: beyond the furthest sale made past the stop.

    A sale short of the stop -- a profit taken on the way out -- passes none of them. A
    sale beyond OUT BY passes all of them.
    """
    sgn = sign(side)
    past = [float(p) for p, q in dict(sold_levels or {}).items()
            if q and sgn * (stop - float(p)) > 1e-9]
    if not past:
        return list(levels)
    furthest = min(past) if sgn > 0 else max(past)
    return [p for p in levels if sgn * (furthest - p) > 1e-9]


def weights(levels: list[float], avg: float, side: str) -> list[float]:
    """Equal loss: one over what a lot cut at each rung loses.

    Flat when the book is not under water across the whole band -- an average at or past
    a rung, which only fills typed beyond the stop can produce -- since equal loss means
    nothing there.
    """
    sgn = sign(side)
    gaps = [sgn * (avg - x) for x in levels]
    if not gaps or min(gaps) <= 1e-9:
        return [1.0] * len(levels)
    return [1.0 / g for g in gaps]


def average(avg: float | None, levels: list[float], side: str) -> float | None:
    """The price the cut averages out at, unrounded: for sizing, where a book on at `avg`
    is stopped. None when there are no rungs to cut at."""
    if not levels or avg is None or avg != avg:
        return None
    w = weights(levels, avg, side)
    return sum(x * v for x, v in zip(levels, w)) / sum(w)


def reference(avg: float | None, levels: list[float], side: str,
              fallback: float) -> float:
    """What a book's loss is measured to: the cut's average, or `fallback` (OUT BY) once
    every rung of the cut is behind you."""
    ref = average(avg, levels, side)
    return fallback if ref is None else ref


def loss_bp(position: int, avg: float | None, levels: list[float], side: str,
            fallback: float) -> float:
    """Lot-bp a book loses cut through every rung ahead of it. Unrounded, so it is the
    bound: the whole lots `allocate` cuts never lose more than this."""
    if not position or avg is None or avg != avg:
        return 0.0
    return position * sign(side) * (avg - reference(avg, levels, side, fallback))


def allocate(position: int, levels: list[float], avg: float, side: str) -> list[int]:
    """Lots per cut rung, summing to the position EXACTLY.

    Floored, then the remainder -- fewer lots than there are rungs -- goes one each to the
    rungs nearest the stop. Put anywhere else it would be cut at a worse price, and the
    whole lots could lose more than the unrounded split the way in was sized to.
    """
    m = len(levels)
    if m == 0:
        return []
    if position <= 0:
        return [0] * m
    w = weights(levels, avg, side)
    tot = sum(w)
    lots = [int(position * x / tot) for x in w]
    for i in range(position - sum(lots)):
        lots[i % m] += 1
    return lots


def plan(avg: float | None, position: int, stop: float, out_by: float, side: str,
         instrument: str = "SR3", tick: float = TICK, sold_levels=None) -> dict:
    """One cut for a book of `position` lots on at `avg`: the rungs, the lots at each, what
    each loses, and what is left after each.

    `loss` is the unrounded bound the tables report; `loss_lots` what the whole lots lose,
    never more.
    """
    dpb = DOLLARS_PER_BP[instrument]
    sgn = sign(side)
    every = cut_levels(stop, out_by, side, tick)
    ahead = ahead_levels(every, sold_levels, stop, side)
    position = max(0, int(position or 0))
    live = position > 0 and avg is not None and avg == avg
    lots = allocate(position, ahead, avg, side) if live else [0] * len(ahead)
    loss_at = [q * sgn * (avg - x) * dpb if live else 0.0 for q, x in zip(lots, ahead)]
    left, n = [], position
    for q in lots:
        n -= q
        left.append(n)
    return {
        "instrument": instrument, "side": side, "stop": stop, "out_by": out_by,
        "all_levels": every, "levels": ahead,
        "passed": [p for p in every if p not in set(ahead)],
        "lots": lots, "left": left, "loss_at": loss_at,
        "position": position, "avg": avg,
        "avg_cut": average(avg, ahead, side) if live else None,
        "loss": loss_bp(position, avg, ahead, side, out_by) * dpb if live else 0.0,
        "loss_lots": sum(loss_at),
    }


def _sized(lp: dict) -> list[dict]:
    """The rows the cap is checked on: the book before any sale (`cap_rows`), since a sale
    never changes the way in (desk, 2026-10-08). A plan without them uses its rows."""
    return lp.get("cap_rows") or lp.get("rows") or []


def _full(lp: dict):
    """The full fill's book, (lots, average), or None with nothing on."""
    rows = [r for r in _sized(lp) if r["pos"] > 0]
    return (rows[-1]["pos"], rows[-1]["avg"]) if rows else None


def fit_in(plan_at, levels: list[float], side: str, max_loss: float, dpb: float,
           banked_bp: float = 0.0, fallback: float | None = None,
           start: float | None = None) -> tuple[dict, float]:
    """The way in, sized so the book at EVERY depth cut through `levels` loses at most
    max loss.

    `plan_at(ref, budget)` is the way in -- `ladder.plan` with its risk measured to `ref`
    and `budget` as its max loss. Two steps:

    - **The reference.** The cut's average depends on the book's average, which depends
      on the lots, which depend on the reference -- so it is iterated: sized to the stop
      (`start`), then to the full fill's cut average, until it stops moving. It barely
      moves, so a few passes do it.
    - **The cap** (desk, 2026-09-29), exactly, at every depth (2026-10-04). Each depth's
      book cut through every rung must not exceed max loss -- the book as if nothing were
      sold (`_sized`): what sales bank is booked P&L, never more room (desk, 2026-10-08).
      `banked_bp` is subtracted only if a caller passes it; the Trade page does not. Usually the full fill is the worst depth, since each lot added only adds
      to the loss -- but not when fills sit past the stop. While a book's average is at
      or past a cut rung the cut is split evenly (`weights`), and a shallower depth can
      lose more than the full fill. So: if the full fill is over -- whole lots, or the
      reference still settling -- the budget handed to the way in comes down by the
      excess until it fits; then every depth is checked, and if a shallower one is still
      over, halving finds the largest budget at which they all fit.

    Returns the plan and the reference it was sized to. With nothing to size (no max
    loss, or a filled book already over it on its own) the budget bottoms out at zero
    and the plan adds nothing.
    """
    ref = start if start is not None else fallback
    lp = plan_at(ref, max_loss)
    for _ in range(12):
        book = _full(lp)
        if book is None:
            break
        new = reference(book[1], levels, side, fallback)
        if abs(new - ref) < 1e-9:
            break
        ref = new
        lp = plan_at(ref, max_loss)

    budget = max_loss
    for _ in range(24):
        book = _full(lp)
        if book is None or budget <= 0:
            break
        over = (loss_bp(*book, levels, side, fallback) - banked_bp) * dpb - max_loss
        if over <= 1e-6:
            break
        budget = max(0.0, budget - over - 0.01)
        lp = plan_at(ref, budget)

    def worst_over(p: dict) -> float:
        """Dollars the worst depth's book, cut through the band, is over max loss."""
        rows = [r for r in _sized(p) if r["pos"] > 0]
        worst = max(((loss_bp(r["pos"], r["avg"], levels, side, fallback) - banked_bp) * dpb
                     for r in rows), default=0.0)
        return worst - max_loss

    # The guarantee is on every depth (2026-10-04). When a shallower one is still over,
    # the largest budget at which every depth fits is found by halving; when the filled
    # book alone is over, none does, and the way in adds nothing.
    if worst_over(lp) > 1e-6 and budget > 0:
        best, lo, hi = plan_at(ref, 0.0), 0.0, budget
        for _ in range(30):
            mid = (lo + hi) / 2
            trial = plan_at(ref, mid)
            if worst_over(trial) <= 1e-6:
                best, lo = trial, mid
            else:
                hi = mid
        lp = best
    lp["max_loss"] = max_loss
    return lp, ref


def restate(rows: list[dict], levels: list[float], side: str, dpb: float,
            fallback: float, banked_bp: float = 0.0) -> list[dict]:
    """The fill-depth rows' loss, restated as each depth's own book cut through the band.

    `ladder.depth_table` measures every depth to the one price the way in was sized to.
    The cut's average moves a little with each depth's average, so each row is given its
    own, and the table says exactly what that depth loses if it is cut through OUT BY.
    """
    for r in rows:
        r["risk_bp"] = loss_bp(r["pos"], r["avg"], levels, side, fallback) - banked_bp
        r["loss"] = r["risk_bp"] * dpb
        r["rr"] = (r["pnl"] / r["loss"]) if r["loss"] > 0 else float("nan")
    return rows
