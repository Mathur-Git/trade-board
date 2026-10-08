"""
Scaling out: a position you already hold, partitioned across levels on the way out.

The constraint is not the scale-in's. Going in, size is the unknown -- you choose how
many lots to commit against a loss budget, and the constraint is an inequality: spend at
most `max_loss`. Coming out, size is settled, and the lots sold across the rungs must add
up to the position exactly. A partition, not an allocation.

The rule: equal regret
----------------------
The exact dual of the scale-in's equal risk, with the stop swapped for the target.

    scaling in    a lot costs  |p - stop|    -- what it loses if stopped
    scaling out   a lot costs  |target - p|  -- what it GIVES UP if the move runs on

Equalise each rung's share of that second quantity and

    q  proportional to  1 / |target - p|

so lots rise as you work further out: a lot sold near the target forgoes almost nothing,
a lot sold near your entry forgoes the whole move. It produces very nearly the same shape
as equal risk read backwards -- 21.0 down to a 19.0 stop on $5k gives 25/33/50/101, and
21.0 out to a 23.0 target on 200 lots gives 24/32/48/96.

It inherits the same degeneracy and takes the same fix. A lot sold AT the target forgoes
nothing and would take unbounded size, so `last` is the boundary beyond the final rung
rather than a rung itself -- exactly as the scale-in excludes its stop.

A peak on equal regret (desk, 2026-09-29)
-----------------------------------------
The way in's peak, mirrored: the dollars of upside each rung gives up follow a bell curve
centred on a level you pick, instead of lying flat. Same kernel, same widths
(`ladder.peak_weights`, `ladder.PEAK_WIDTHS`), with the width a share of first exit to
flat-by. Equal regret is this with an infinite width.

It is NOT free the way the in-side peak is. Going in, the budget is fixed and the peak
only moves dollars between rungs. Coming out, the LOTS are fixed, so total regret --
``position * |target - avg out|`` -- moves with the peak: every dollar of regret the
peak adds is average exit given up. What it buys is the back-loading equal regret is
known for. Long 200, 21.0 out to 25.0, Medium: flat is 9/10/12/15/18/25/37/74 at 23.54
with 31 sold by 22.0; peaked at 23.0 it is 3/7/13/22/30/36/40/49 at 23.46; at 22.0 it
is 16/24/31/34/32/26/20/17 at 22.71 with 71 sold by 22.0. The hump is in the regret
dollars, not the lots -- dividing by regret per lot still leans the lots toward the
target unless the peak sits early.

What it buys and what it costs
------------------------------
A better average exit if you get there: 22.04 against 21.75 for a flat ladder on the
example above. The cost is that it is back-loaded, so a reversal finds you heavier --
56 of 200 sold by 21.5 where flat would have sold 100. That is the real asymmetry between
the two sides. A rung you never reach on the way in leaves you light and onside; one you
never reach on the way out leaves you heavy and it is coming back. What manages that is
the core/flip split, not the shape of this ladder.

Risk-free is kept as a MARKER, not as the rule. The rung at which realised profit first
covers what the remainder gives back at the stop is worth seeing. It is just not worth
sizing around, because sizing around it throws away the average -- it sells about half
the position at the first rung, which is the worst average exit available.

What the average does, and does not, do
---------------------------------------
Selling part of a position does not move the average of what is left: a partial sale
realises profit, it does not change the cost basis. So the breakeven of the remainder is
the same `A` throughout, which is why the page draws one line and leaves it there.

What you have already sold
--------------------------
The exit's mirror of the scale-in's held lots. Lots already sold are banked against the
cost basis they came from, and what is still on is split across the rungs AHEAD of the
furthest one you sold at -- the market has been through the ones behind it, so the rest
of the position is not spread back over prices you have already worked.

Lots carried outside the ladder
-------------------------------
The flip allowance is held but not sold through this ladder. It is still on at a
stop-out -- the edge it goes back on at sits on the losing side, so a trade falling to
its stop has put it back -- so it counts in every stop-side number (open risk, if
stopped, and so the risk-free rung) and in none of the upside ones.
"""

from __future__ import annotations

import math

from ladder import DOLLARS_PER_BP, TICK, sign          # noqa: F401  (re-exported)


def exit_levels(first: float, last: float, side: str,
                tick: float = TICK) -> list[float]:
    """Rungs from the first exit toward `last`, with `last` itself excluded.

    `last` is the level you are flat by, not a rung you work. Excluding it mirrors the
    scale-in excluding its stop, and for the same reason: a lot sold there forgoes
    nothing, so equal regret would put unbounded size on it.
    """
    sgn = sign(side)
    steps = int(round(sgn * (last - first) / tick))
    if steps < 1:
        return []
    return [round(first + sgn * i * tick, 6) for i in range(steps)]


def regret_weights(levels: list[float], last: float, side: str,
                   peak: float | None = None, width: float | None = None) -> list[float]:
    """Relative weights giving every rung the same share of the upside forgone -- or,
    with a `peak` and `width` (bp), a share on a bell curve centred on the peak:
    ``2 ** -((p - peak) / width) ** 2``, half the peak's at one width. Dividing by the
    regret per lot turns a share into lots, exactly as the way in divides by risk."""
    sgn = sign(side)
    shaped = peak is not None and bool(width) and width > 0
    out = []
    for p in levels:
        gap = sgn * (last - p)
        share = 2.0 ** (-((p - peak) / width) ** 2) if shaped else 1.0
        out.append(share / gap if gap > 0 else 0.0)
    return out


def regret_at(level: float, lots: int, last: float, side: str, dpb: float) -> float:
    """Dollars of upside `lots` sold at `level` give up if the move runs on to `last`:
    the quantity equal regret splits evenly and the peak bends."""
    return lots * sign(side) * (last - level) * dpb


def allocate(position: int, levels: list[float], last: float, side: str,
             peak: float | None = None, width: float | None = None) -> list[int]:
    """Lots per rung, summing to the position EXACTLY.

    Equality, not a ceiling -- these are lots you already hold, so anything left over is
    a lot you forgot to sell. That is the one place the arithmetic differs from the
    scale-in, where overshooting the budget is the error to avoid and undershooting is
    merely untidy. The remainder from integer division goes to the largest fractional
    parts, which keeps the shape instead of dumping it on one rung.
    """
    m = len(levels)
    if m == 0:
        return []
    if position <= 0:
        return [0] * m
    w = regret_weights(levels, last, side, peak, width)
    tot = sum(w)
    if tot <= 0:
        each, extra = divmod(position, m)
        return [each + (1 if i < extra else 0) for i in range(m)]
    raw = [position * x / tot for x in w]
    lots = [int(x) for x in raw]
    order = sorted(range(m), key=lambda i: raw[i] - int(raw[i]), reverse=True)
    for i in order[:position - sum(lots)]:
        lots[i] += 1
    return lots


def ahead_levels(levels: list[float], sold_levels, side: str) -> list[float]:
    """The rungs still in front of you: beyond the furthest one you have sold at.

    Once a long has sold at 21.0 on the way up, 20.5 and 21.0 are behind it -- the market
    has been through them -- so what is still on is split across the rungs beyond, not
    spread back over prices already worked. A sale short of the first exit (a trim at
    20.0 on a ladder starting at 20.5) passes nothing, so every rung stays ahead.
    """
    sold = [float(p) for p, q in dict(sold_levels or {}).items() if q]
    if not sold:
        return list(levels)
    sgn = sign(side)
    furthest = max(sold) if sgn > 0 else min(sold)
    return [p for p in levels if sgn * (p - furthest) > 1e-9]


def breakeven_lots(position: int, avg: float, stop: float, first: float,
                   side: str = "buy", carried: int = 0, banked_bp: float = 0.0) -> int:
    """Lots at the first exit that would make the remainder unable to lose.

    A marker, not the sizing rule. Selling q at the first exit banks `q (E1 - A)`, and
    everything else still on -- the rest of the ladder plus any carried lots -- gives
    back `(A - S)` a lot at the stop, less whatever is already banked. q is where the two
    meet, rounded up and capped at the position: carried lots are not sold here.
    """
    sgn = sign(side)
    span = sgn * (first - stop)
    if span <= 0 or position <= 0:
        return 0
    q = ((position + carried) * sgn * (avg - stop) - banked_bp) / span
    if q <= 0:
        return 0
    return min(position, int(math.ceil(q - 1e-9)))


def reversal_table(levels: list[float], lots: list[int], position: int, avg: float,
                   stop: float, dpb: float, side: str, flat: float | None = None,
                   carried: int = 0, sold: int = 0, banked_bp: float = 0.0,
                   sold_notional: float = 0.0) -> list[dict]:
    """One row per rung reached: sold what, banked what, carrying what.

    Depth 0 is where you stand now, with whatever you have already sold banked in it.
    `if_stopped` is the whole trade if it turns here and runs to the stop -- realised
    profit less what everything still on gives back, carried lots included -- and it is
    the number that says when the trade stopped being able to lose. `if_runs` is the
    other tail: what is left of the ladder rides to `flat`, the level you are flat by,
    which is the same level the page's "holding all of it" figure is measured to.
    """
    sgn = sign(side)
    risk_lot = sgn * (avg - stop)                 # bp given back per lot at the stop
    flat = (levels[-1] if levels else avg) if flat is None else flat
    out = []
    n_sold, realised_bp, notional = int(sold), float(banked_bp), float(sold_notional)

    def row(depth, level, q):
        left = position - (n_sold - sold)
        exposed = left + carried
        realised = realised_bp * dpb
        at_stop = realised - exposed * risk_lot * dpb
        return {
            "depth": depth, "level": level, "lots": q, "sold": n_sold, "left": left,
            "realised": realised,
            "open_risk": exposed * risk_lot * dpb,
            "if_stopped": at_stop,
            "if_runs": realised + left * sgn * (flat - avg) * dpb,
            "free": at_stop >= 0,
            "avg_out": notional / n_sold if n_sold else float("nan"),
        }

    out.append(row(0, avg, 0))
    for d, (p, q) in enumerate(zip(levels, lots), start=1):
        n_sold += q
        notional += q * p
        realised_bp += q * sgn * (p - avg)
        out.append(row(d, p, q))
    return out


def plan(avg: float, position: int, stop: float, first: float, last: float, side: str,
         instrument: str = "SR3", excluded=None, tick: float = TICK,
         sold_levels=None, sold_basis: float | None = None, carried: int = 0,
         peak: float | None = None, width: float | None = None) -> dict:
    """One complete exit ladder.

    `peak` and `width` (bp) put the regret on a bell curve centred on the peak instead of
    flat; either missing means equal regret. The curve is a function of PRICE, so a
    skipped rung drops out and the rest re-split in proportion.

    `side` is the side of the POSITION -- "buy" for a long being sold, "sell" for a short
    being covered -- so it matches the scale-in page's vocabulary rather than inventing a
    second one.

    `position` is what is still on and still to be sold through this ladder. Lots already
    sold come in as `sold_levels`, banked against `sold_basis` -- the average they were
    bought at, which is not always `avg`: on the Trade page the lots you sold came out of
    the held position, while `avg` is the blended book after adding. `carried` lots are
    held but not sold here (the flip allowance) and count on the stop side only.

    Skipped rungs are dropped before the split, exactly as on the way in, so their lots
    go to the rungs that remain rather than being left unsold.
    """
    dpb = DOLLARS_PER_BP[instrument]
    sgn = sign(side)
    position = max(0, int(position or 0))
    carried = max(0, int(carried or 0))

    sold_map = {round(float(p), 6): int(q)
                for p, q in dict(sold_levels or {}).items() if q and int(q) > 0}
    basis = avg if sold_basis is None else sold_basis
    n_sold = sum(sold_map.values())
    banked_bp = sum(q * sgn * (p - basis) for p, q in sold_map.items())
    sold_notional = sum(p * q for p, q in sold_map.items())

    all_levels = exit_levels(first, last, side, tick)
    ahead = ahead_levels(all_levels, sold_map, side)
    excl = {round(float(x), 6) for x in (excluded or ())}
    live = [p for p in ahead if p not in excl]

    shaped = peak is not None and bool(width) and width > 0
    lots = allocate(position, live, last, side,
                    peak if shaped else None, width if shaped else None)
    rows = reversal_table(live, lots, position, avg, stop, dpb, side, flat=last,
                          carried=carried, sold=n_sold, banked_bp=banked_bp,
                          sold_notional=sold_notional)
    full = rows[-1] if rows else None
    free_now = bool(rows) and rows[0]["free"] and (position + carried) > 0

    return {
        "instrument": instrument, "side": side,
        "dollars_per_bp": dpb, "tick_value": dpb * tick,
        "avg": avg, "position": position, "stop": stop,
        "first": first, "last": last,
        "peak": peak if shaped else None, "width": width if shaped else None,
        "all_levels": all_levels, "ahead": ahead,
        "passed": [p for p in all_levels if p not in set(ahead)],
        "levels": live, "lots": lots,
        "excluded": sorted(excl, reverse=(side == "buy")),
        "rows": rows,
        "sold": n_sold, "sold_levels": sold_map, "banked": banked_bp * dpb,
        "carried": carried,
        "avg_out": full["avg_out"] if full else float("nan"),
        "breakeven_lots": (breakeven_lots(position, avg, stop, live[0], side, carried,
                                          banked_bp) if live else 0),
        "open_risk": (position + carried) * sgn * (avg - stop) * dpb,
        "max_win": (banked_bp + position * sgn * (last - avg)) * dpb,
        "free_now": free_now,
        "free_at": (None if free_now else
                    next((r["depth"] for r in rows if r["free"] and r["depth"] > 0), None)),
    }
