"""
Scale-in allocation on the ladder: how many lots, at what price, for a given max loss.

The whole tool is one constraint. Stopped out of a position built at levels ``p_i`` with
``q_i`` lots on each, the loss is

    sum_i  q_i * |p_i - stop| * dollars_per_bp

and the sizing rule is the one way that budget is spent: EQUAL RISK, every level
putting the same dollars at risk. A lot is not equally expensive everywhere -- one
entered far from the stop costs more of the budget than one entered near it -- so an
even split of dollars buys uneven lots, fewer at the top and more toward the stop.

Equal risk can be given a PEAK (desk, 2026-09-27): the dollars at risk follow a bell
curve centred on a level you pick, instead of lying flat. See `peak_weights`. Flat is
still the rule with no peak; the peak only tilts the same one budget.

Which is why "borrowing lots from higher levels" is exact rather than a figure of
speech. A lot entered far from the stop consumes more budget than one entered near it,
so excluding a far level frees disproportionately more size than excluding a near one.
Exclusions re-allocate for free: there is no rule for it, it falls out of the budget
line.

Sign
----
`side` is "buy" or "sell", and everything is written through `sgn` -- +1 buying, -1
selling. Risk per lot is ``sgn * (p - stop)`` and reward per lot at the target is
``sgn * (target - p)``, both positive for a well-formed trade in either direction.

This is the LADDER's sign, not the board's. lib/curve.py is price space and lib/meets.py
is rate space; here "buy" just means long whatever the ladder quotes, which for an SR3
butterfly is the fly price itself.

Held position
-------------
A position already on is charged against the same budget: `max_loss` is what the trade
may cost in total, not what the remainder of it may cost. So lots already carried shrink
the ladder beneath them. That is the point -- it answers "I am long 50 at 21.2, how much
more can I add before I am risking more than I said" -- and it means a position that
already risks the whole budget leaves nothing to work with, which the plan reports
rather than silently sizing to zero.

Fill depth
----------
The headline output is deliberately NOT a risk-reward number. With a scale-in, R:R is
path dependent -- it turns on how far the market went before it reversed, which is the
one thing you do not know when you set the ladder. Any single figure has to assume the
full fill, which is the case you least expect. So `depth_table` reports one row per
number of levels filled. The shallow rows are where you find out whether the plan is too
light to be worth doing, and the deep rows are where you find out whether it is too
heavy; that trade-off is the whole problem and it does not compress to one number.

Budget is spent once, not scraped
---------------------------------
Lots are integers, so the ideal weights never land exactly on the budget.
Sizes are floored and then topped up by largest fractional remainder, one pass, checking
the budget at each step. A second pass would spend the last scraps -- but only on the
cheapest levels, which are the ones nearest the stop, quietly turning a flat ladder into
a bottom-heavy one. The remainder is left unspent and reported instead.
"""

from __future__ import annotations

import math

TICK = 0.5          # bp. The ladder grid is half a basis point.

#: Dollars per basis point, per lot. A tick is half a bp, so a tick is half of these.
#: Desk-supplied; note the repo does not cite contract specs -- see README, open items.
DOLLARS_PER_BP = {"SR3": 25.0, "ZQ": 125.0 / 3.0}       # 25.00 and 41.67

def sign(side: str) -> float:
    return 1.0 if side == "buy" else -1.0


def entry_levels(entry: float, stop: float, side: str, tick: float = TICK) -> list[float]:
    """Levels you can work, from the entry toward the stop, with the stop excluded.

    Excluding the stop is deliberate. A lot resting there carries no risk, so equal-risk
    sizing would put unbounded size on it. It is also not a level anyone works -- being
    filled there and being stopped there are the same event.
    """
    sgn = sign(side)
    steps = int(round(sgn * (entry - stop) / tick))
    if steps < 1:
        return []
    return [round(entry - sgn * i * tick, 6) for i in range(steps)]


def risk_per_lot(levels: list[float], stop: float, side: str) -> list[float]:
    """Basis points at risk on one lot at each level, if the stop is hit."""
    sgn = sign(side)
    return [sgn * (p - stop) for p in levels]


def equal_risk_weights(risk: list[float]) -> list[float]:
    """Relative weights that put the same dollars at risk on every level.

    A lot at a level `r` basis points from the stop risks `r` times the unit, so
    weighting by `1/r` makes each level's contribution to the maximum loss identical.
    The budget then splits evenly across levels and each one buys whatever that slice
    affords -- which is fewer lots at the top of the ladder and more near the stop.
    """
    return [1.0 / r if r > 0 else 0.0 for r in risk]


#: How wide the peak is, as a share of the entry-to-stop distance (desk, 2026-09-27). A
#: share rather than a fixed bp so that a name means the same shape on every trade: the
#: stop distance already says how much the structure moves. Three, not five -- on a
#: ladder of eight or so rungs, finer steps differ by about a lot, which rounding eats.
PEAK_WIDTHS = {"broad": 1 / 2, "medium": 1 / 3, "narrow": 1 / 5}


def peak_width(mode: str, entry: float, stop: float) -> float | None:
    """The half-width in bp for a width mode on this ladder; None for no peak."""
    share = PEAK_WIDTHS.get(mode)
    return share * abs(entry - stop) if share else None


def peak_weights(levels: list[float], risk: list[float], peak: float,
                 width: float) -> list[float]:
    """Lot weights that put the dollars at risk on a bell curve centred on `peak`.

    A level `width` bp from the peak takes half the peak's risk, one twice as far a
    sixteenth: share ``2 ** -((p - peak) / width) ** 2``. Dividing by the risk per lot
    turns a share of the budget into lots, exactly as `1/r` does for equal risk -- which
    is this with an infinite width. The ends are not set; they fall where the curve puts
    them, so a peak off-centre is steeper on its short side without being told to.

    Why a peak at all: the risk worth putting on a level is roughly the chance it trades
    there times how good the price is there. The first falls toward the stop and the
    second rises toward it, so the product rises and then falls.
    """
    return [2.0 ** (-((p - peak) / width) ** 2) / r if r > 0 else 0.0
            for p, r in zip(levels, risk)]


def allocate(risk: list[float], weights: list[float],
             budget_bp: float) -> list[int]:
    """Integer lots per level, spending at most `budget_bp` lot-basis-points of risk.

    Floor first and top up by largest remainder, never round to nearest: rounding to
    nearest can overshoot, and overshooting a stated maximum loss is the one error this
    tool must not make.
    """
    if not risk:
        return []
    denom = sum(w * r for w, r in zip(weights, risk))
    if denom <= 0 or budget_bp <= 0:
        return [0] * len(risk)
    k = budget_bp / denom
    raw = [k * w for w in weights]
    lots = [int(x) for x in raw]
    used = sum(q * r for q, r in zip(lots, risk))
    order = sorted(range(len(risk)), key=lambda i: raw[i] - int(raw[i]), reverse=True)
    for i in order:
        if used + risk[i] <= budget_bp + 1e-9:
            lots[i] += 1
            used += risk[i]
    return lots


def depth_table(levels: list[float], lots: list[int], stop: float, target: float,
                dpb: float, side: str, held: int = 0,
                held_avg: float | None = None, banked_bp: float = 0.0) -> list[dict]:
    """One row per fill depth: filled the first d levels, then what?

    `loss` is being stopped from that depth. `pnl` is reaching the target from it. The
    pair is the honest answer to "what if it turns here", and the shallow rows are the
    ones worth reading -- they are the likely ones.

    A position already on carries into every row, and gets a row of its own at depth 0:
    where you stand before the ladder does anything. Averages below it are blended, so
    what you read is the real book, not the increment. Profit already banked from lots
    sold out of it (`banked_bp`, lot-bp, positive is profit) comes off every loss and
    onto every P&L -- it is money the trade has already made. Zero on the Ladder page.
    """
    sgn = sign(side)
    out: list[dict] = []
    pos = int(held or 0)
    notional = pos * float(held_avg or 0.0)
    risk_bp = pos * sgn * (float(held_avg or 0.0) - stop) - banked_bp

    if pos:
        loss = risk_bp * dpb
        pnl = (pos * sgn * (target - held_avg) + banked_bp) * dpb
        out.append({
            "depth": 0, "level": float(held_avg), "lots": pos, "pos": pos,
            "avg": float(held_avg), "risk_bp": risk_bp, "loss": loss, "pnl": pnl,
            "rr": (pnl / loss) if loss > 0 else float("nan"), "held": True,
        })

    for d, (p, q) in enumerate(zip(levels, lots), start=1):
        pos += q
        notional += q * p
        risk_bp += q * sgn * (p - stop)
        avg = notional / pos if pos else float("nan")
        loss = risk_bp * dpb
        pnl = (pos * sgn * (target - avg) + banked_bp) * dpb if pos else 0.0
        out.append({
            "depth": d, "level": p, "lots": q, "pos": pos, "avg": avg,
            "risk_bp": risk_bp, "loss": loss, "pnl": pnl,
            "rr": (pnl / loss) if loss > 0 else float("nan"), "held": False,
        })
    return out


def blend(held_levels) -> tuple[int, float | None]:
    """Per-level fills -> one position: total lots and the average they are on at.

    Lossless for risk, which is the only reason the rest of the module can go on
    working in (lots, average) terms. Risk is `sum q_i (p_i - stop)`, and that equals
    `lots * (avg - stop)` identically, so blending throws nothing away -- it is the same
    number arrived at from the other side.

    This is also the input a desk actually has. Nobody remembers the exact average of a
    scaled-in position, but everybody remembers taking 30 at 20.5.
    """
    items = [(float(p), int(q)) for p, q in dict(held_levels or {}).items() if q]
    lots = sum(q for _, q in items)
    if not lots:
        return 0, None
    return lots, sum(p * q for p, q in items) / lots


def plan(entry: float, stop: float, target: float, max_loss: float, side: str,
         instrument: str = "SR3", excluded=None, tick: float = TICK,
         held: int = 0, held_avg: float | None = None,
         held_levels=None, sold_lots: int = 0, sold_bp: float = 0.0,
         peak: float | None = None, width: float | None = None,
         risk_to: float | None = None) -> dict:
    """One complete ladder: levels, lots, and what the position does at each depth.

    `peak` and `width` (bp) put the risk on a bell curve centred on the peak instead of
    flat (`peak_weights`); either missing means equal risk. The curve is a function of
    PRICE, so an excluded level drops out and the rest re-split in proportion, and one
    skip never reshapes the others.

    `risk_to` is the price the risk is measured to when that is not the stop (desk,
    2026-09-30). With a cut past the stop (lib/cuts.py) it is the cut's average -- for
    sizing, where the whole position is really stopped -- so max loss covers the trade
    all the way to OUT BY. The rungs still run from the entry to the stop, which is where
    adding ends; only the budget's arithmetic moves. None is the stop, as before.

    `excluded` levels are dropped before allocation rather than zeroed afterwards --
    that is exactly what makes their budget available to everything else.

    Held lots are two different things
    ----------------------------------
    A lot held on a rung the ladder is working is a FILL against that rung's plan. A lot
    held anywhere else -- a pulled rung, a price off the ladder -- is a position you had
    before the plan. They used to be treated alike, and that was wrong: 7 filled of a
    planned 16 at 1.0 was charged to the budget as a prior position and the rest re-split
    over every rung, so 1.0 was told to take 13 MORE (20, over plan) and 0.5 dropped from
    26 to 20 -- a partial fill moved size to the worse price. Now (desk, 2026-09-24):

    - **Prior position** is charged against the SAME budget, because `max_loss` is what
      the trade may cost in total. It shrinks the ladder beneath it, and a prior position
      that already risks the whole budget leaves nothing, reported via `over_budget`.
    - **Fills** count against their rung. The plan is sized once, on what the prior
      position leaves; a rung part-filled shows what is LEFT (16 planned, 7 filled: 9),
      and every other rung keeps its size.
    - **Overfill** -- more filled than planned at a rung -- is risk the plan did not
      budget for, so it comes out of the rungs with no fills yet, re-split by the same
      equal-risk rule (or the peak, when there is one).
    - **The cap** (desk, 2026-09-29): what is on plus what is left to work never exceeds
      `max_loss`. When the rungs with no fills cannot absorb an overfill -- every rung
      part-filled, say -- the rest comes off what is left on the rungs nearest the stop.

    `lots` is therefore what is still to work at each rung; `plan` is the rung's full
    size and `filled` what has come in.

    Sold out of it
    --------------
    `sold_lots` sold out of the held position come off it at the same average -- a
    partial sale does not move the cost basis -- and both the risk they no longer carry
    and `sold_bp` (lot-bp they banked, positive is profit) are credited to the budget:
    the max loss is what the trade may cost IN TOTAL, and profit already banked is part
    of that total. Both zero on the Ladder page, which never sells.
    """
    dpb = DOLLARS_PER_BP[instrument]
    sgn = sign(side)
    ref = stop if risk_to is None else float(risk_to)     # what the risk is measured to
    all_levels = entry_levels(entry, stop, side, tick)
    excl = {round(float(x), 6) for x in (excluded or ())}
    live = [p for p in all_levels if p not in excl]
    risk = risk_per_lot(live, ref, side)
    shaped = peak is not None and bool(width) and width > 0

    def weights(levels, r):
        return peak_weights(levels, r, peak, width) if shaped else equal_risk_weights(r)

    # Per-rung held lots; a bare (held, held_avg) pair has no rungs, so all of it is prior.
    held_map = {round(float(k), 6): int(v)
                for k, v in dict(held_levels or {}).items() if v and int(v) > 0}
    live_set = set(live)
    fills = {p: q for p, q in held_map.items() if p in live_set}
    prior = {p: q for p, q in held_map.items() if p not in live_set}
    if held_levels:
        held_all, havg = blend(held_map)
        prior_n, prior_avg = blend(prior)
    else:
        held_all = int(held or 0)
        havg = float(held_avg) if held_all and held_avg is not None else None
        prior_n, prior_avg = held_all, havg

    # Nothing held means nothing to have sold from, so a stray sale is ignored here and
    # the page says so.
    sold_lots = min(max(0, int(sold_lots or 0)), held_all) if held_all else 0
    if not sold_lots:
        sold_bp = 0.0
    total_bp = max_loss / dpb if dpb else 0.0
    prior_risk_bp = prior_n * sgn * (prior_avg - ref) if prior_n else 0.0
    sold_credit_bp = (sold_lots * sgn * (havg - ref) if sold_lots else 0.0) + sold_bp

    # The plan: sized once, on what the prior position and any sales leave.
    budget_bp = max(0.0, total_bp - prior_risk_bp + sold_credit_bp)
    planned = allocate(risk, weights(live, risk), budget_bp)

    # Fills against it. Overfill comes out of the rungs with nothing filled yet.
    got = [fills.get(p, 0) for p in live]
    over_bp = sum(max(g - q, 0) * r for g, q, r in zip(got, planned, risk))
    if over_bp > 0:
        open_i = [i for i, g in enumerate(got) if g == 0]
        room = sum(planned[i] * risk[i] for i in open_i) - over_bp
        r_open = [risk[i] for i in open_i]
        redo = allocate(r_open, weights([live[i] for i in open_i], r_open),
                        max(0.0, room))
        for i, q in zip(open_i, redo):
            planned[i] = q
    lots = [max(q - g, 0) for q, g in zip(planned, got)]      # what is left to work

    # The cap (desk, 2026-09-29). Max loss is a hard limit on what is on plus what is
    # left to work, whatever the fills, the peak or the skips. The overfill step above
    # only draws on rungs with nothing filled, so when every rung is part-filled the
    # extra was kept and the ladder went over. Whatever is still over comes off the
    # rungs nearest the stop first, so the rungs likely to fill next keep their size.
    net = max(0, held_all - sold_lots)
    held_risk_bp = net * sgn * (havg - ref) if net and havg is not None else 0.0
    held_risk_bp -= sold_bp
    excess = held_risk_bp + sum(q * r for q, r in zip(lots, risk)) - total_bp
    for i in reversed(range(len(lots))):
        if excess <= 1e-9:
            break
        if lots[i] and risk[i] > 0:
            cut = min(lots[i], math.ceil(excess / risk[i] - 1e-9))
            lots[i] -= cut
            excess -= cut * risk[i]
    target_lots = [g + q for g, q in zip(got, lots)]

    # The book as it stands -- prior position and fills, less what was sold -- with the
    # rungs adding what is left of them, depth by depth.
    rows = depth_table(live, lots, ref, target, dpb, side, net, havg, sold_bp)
    filled = [r for r in rows if r["pos"] > 0]
    spent = (rows[-1]["risk_bp"] * dpb) if rows else 0.0
    return {
        "instrument": instrument, "side": side,
        "dollars_per_bp": dpb, "tick_value": dpb * tick, "risk_to": ref,
        "peak": peak if shaped else None, "width": width if shaped else None,
        "all_levels": all_levels, "levels": live, "lots": lots,
        "plan": target_lots, "filled": got,
        "fills": {p: q for p, q in fills.items()}, "prior": prior_n,
        "prior_risk": prior_risk_bp * dpb,
        "excluded": sorted(excl, reverse=(side == "buy")),
        "risk": risk, "rows": rows, "full": filled[-1] if filled else None,
        "entry": entry, "stop": stop, "target": target,
        "held": net, "held_avg": havg, "held_risk": held_risk_bp * dpb,
        "sold": sold_lots, "banked": sold_bp * dpb,
        "held_levels": {float(k): int(v) for k, v in held_map.items()},
        "over_budget": held_risk_bp >= total_bp and net > 0,
        "over_by": max(0.0, (held_risk_bp - total_bp) * dpb),
        "new_lots": sum(lots),
        "max_loss": max_loss, "spent": spent, "unspent": max_loss - spent,
        "used_pct": 100.0 * spent / max_loss if max_loss else 0.0,
    }
