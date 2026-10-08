"""The Trade page's money rules -- run from the repo root: python -m pytest tests

Max loss is a hard cap (desk, 2026-09-29): what is filled plus what is left to work,
measured through OUT BY when there is one, never loses more than max loss at ANY depth of
the fill-depth table, and a filled book already over it adds nothing (2026-10-04)."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))
import cuts  # noqa: E402
import ladder  # noqa: E402
import trade_page as tp  # noqa: E402

T = ladder.TICK


def key(p: float) -> str:
    """A rung as the Filled and Sold stores key it: half-bp ticks."""
    return str(int(round(p * 2)))


def setup(**kw) -> dict:
    """The page's own resolved state, from inputs typed as the page receives them."""
    d = dict(inst="SR3", side="buy", mark=None, entry=None, held_map={}, sold_map={},
             stop=None, first=None, target=None, max_loss=None,
             excl_in={"off": [], "on": []}, excl_out={"off": [], "on": []}, depth=None,
             peak=None, shape="off", peak_out=None, shape_out="off", out_by=None)
    d.update(kw)
    return tp._trade_setup(*(d[k] for k in (
        "inst", "side", "mark", "entry", "held_map", "sold_map", "stop", "first", "target",
        "max_loss", "excl_in", "excl_out", "depth", "peak", "shape", "peak_out",
        "shape_out", "out_by")))


def mirror(kw: dict) -> dict:
    """The same trade on the other side: every price negated."""
    m = dict(kw, side="sell" if kw.get("side", "buy") == "buy" else "buy")
    for k in ("mark", "entry", "stop", "first", "target", "out_by"):
        if m.get(k) is not None:
            m[k] = f"{-float(m[k]):g}"
    for k in ("held_map", "sold_map"):
        m[k] = {str(-int(q)): v for q, v in kw.get(k, {}).items()}
    if "excl_in" in kw:
        m["excl_in"] = {a: [-x for x in kw["excl_in"][a]] for a in ("off", "on")}
    return m


def worst_loss(s: dict) -> float:
    return max((r["loss"] for r in s["lp"]["rows"]), default=0.0)


def held_loss(s: dict) -> float | None:
    return next((r["loss"] for r in s["lp"]["rows"] if r["held"]), None)


# Fills past the stop, inside the OUT BY band: a shallow depth's book used to lose more
# than the full fill, and only the full fill was checked. Depth 7 lost $1,662.50 here.
CASE_A = dict(inst="SR3", side="buy", mark="12", held_map={key(4.5): 28}, stop="6.5",
              first="13", target="18.5", max_loss="1547", out_by="2.5")

# What is filled already loses $9,021 cut through OUT BY, $1,429 over a $7,592 cap; the
# way in still added 13 + 20 lots.
CASE_B = dict(inst="ZQ", side="buy", mark="7.0", entry="7.5",
              held_map={key(7.0): 6, key(5.0): 73, key(4.5): 53}, stop="5.5", target="9",
              max_loss="7592", excl_in={"off": [7.0, 6.0], "on": []}, out_by="1.5")


@pytest.mark.parametrize("flip", [False, True], ids=["long", "short"])
def test_every_depth_fits_with_fills_inside_the_cut(flip):
    s = setup(**(mirror(CASE_A) if flip else CASE_A))
    assert worst_loss(s) <= 1547 + 0.01
    assert sum(s["lp"]["lots"]) > 0            # still a ladder, not an empty one


@pytest.mark.parametrize("flip", [False, True], ids=["long", "short"])
def test_a_filled_book_over_the_cap_adds_nothing(flip):
    s = setup(**(mirror(CASE_B) if flip else CASE_B))
    assert sum(s["lp"]["lots"]) == 0
    out_by = "-1.5" if flip else "1.5"
    assert s["cap_note"] == f"filled loses 9,021 cut to {out_by}, 1,429 over max loss"


# The saved Jan27 vs Apr27 plan at a $5,000 cap, with no OUT BY: 65 lots filled lose
# $7,708 at the stop. The title said nothing; the overage was typed into a version note.
CASE_C = dict(inst="ZQ", side="buy", mark="1.5", stop="-2.5", first="1", target="3.5",
              max_loss="5000",
              held_map={key(1.5): 8, key(1.0): 13, key(0.5): 10, key(0.0): 29, key(-1.5): 5})


def test_over_the_cap_is_said_without_out_by():
    s = setup(**CASE_C)
    assert s["cap_note"] == "filled loses 7,708 at the -2.5 stop, 2,708 over max loss"
    assert sum(s["lp"]["lots"]) == 0


def test_no_word_when_the_filled_book_fits():
    assert setup(**dict(CASE_C, max_loss="8000"))["cap_note"] == ""
    assert setup(**dict(CASE_C, max_loss=None))["cap_note"] == ""     # blank: "required"


# Sold past Filled: only as many lots as were filled count, the least profitable first,
# so what the sales bank is never overstated -- it is credited against max loss.
LONG_10 = dict(inst="SR3", side="buy", mark="21", entry="21", stop="19", target="23",
               max_loss="5000", held_map={key(21.0): 10})


@pytest.mark.parametrize("flip", [False, True], ids=["long", "short"])
def test_sold_past_filled_banks_only_the_filled_lots(flip):
    kw = dict(LONG_10, sold_map={key(22.5): 30})
    s = setup(**(mirror(kw) if flip else kw))
    assert s["lp"]["sold"] == 10
    assert s["lp"]["banked"] == pytest.approx(375.0)          # 10 x 1.5bp x $25, not 30
    assert s["ep"]["rows"][0]["realised"] == pytest.approx(375.0)
    assert s["sold_note"] == "30 sold is more than the 10 filled · counting 10"


def test_sold_past_filled_counts_the_least_profitable_first():
    s = setup(**dict(LONG_10, sold_map={key(22.5): 6, key(21.5): 8}))
    assert s["lp"]["banked"] == pytest.approx((8 * 0.5 + 2 * 1.5) * 25)
    # a cut past the stop is a loss, so it counts before any profit
    s = setup(**dict(LONG_10, out_by="18", sold_map={key(18.5): 5, key(22.5): 10}))
    assert s["lp"]["banked"] == pytest.approx((5 * -2.5 + 5 * 1.5) * 25)


def test_sold_within_filled_is_untouched():
    s = setup(**dict(LONG_10, sold_map={key(22.5): 6}))
    assert s["lp"]["banked"] == pytest.approx(6 * 1.5 * 25)
    assert s["sold_note"] == ""


def _random_trade(r: random.Random) -> dict:
    side = r.choice(["buy", "sell"])
    sgn = 1 if side == "buy" else -1
    entry = r.randint(-20, 50) / 2
    stop = entry - sgn * r.randint(1, 14) * T
    out_by = stop - sgn * r.randint(1, 12) * T if r.random() < 0.7 else None
    levels = ladder.entry_levels(entry, stop, side)
    band = cuts.cut_levels(stop, out_by, side) if out_by is not None else []
    held = {}
    for _ in range(r.randint(0, 4)):
        w = r.random()
        if band and w < 0.4:
            p = r.choice(band)                          # past the stop, in the cut
        elif w < 0.8:
            p = r.choice(levels)
        else:
            p = entry + sgn * r.randint(0, 6) * T       # off the ladder, onside
        held[key(p)] = held.get(key(p), 0) + r.randint(1, 80)
    return dict(inst=r.choice(["SR3", "ZQ"]), side=side, mark=f"{entry:g}",
                entry=None if r.random() < 0.2 else f"{entry:g}", held_map=held,
                stop=f"{stop:g}", target=f"{entry + sgn * r.randint(2, 12) * T:g}",
                max_loss=f"{r.randint(200, 20000)}",
                excl_in={"off": sorted(r.sample(levels, r.randint(1, min(3, len(levels)))))
                         if r.random() < 0.3 else [], "on": []},
                shape=r.choice(["off", "off", "medium", "narrow"]),
                peak=r.choice(levels) if r.random() < 0.5 else None,
                out_by=None if out_by is None else f"{out_by:g}")


def test_the_cap_holds_at_every_depth_on_random_trades():
    r = random.Random(20261004)
    for _ in range(300):
        kw = _random_trade(r)
        s = setup(**kw)
        ml, held = s["max_loss"], held_loss(s)
        bound = max(ml, held or 0.0)
        assert worst_loss(s) <= bound + 0.01, kw
        if held is not None and held > ml + 0.01:
            assert sum(s["lp"]["lots"]) == 0, kw
