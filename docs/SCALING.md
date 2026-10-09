# Scaling in, scaling out, and flipping

The position-management side of the board: the `Trade` page, the flip model, and the
measurements behind them. Written 2026-09-21 and kept current, so a session with no
other context can pick this up cold. The `Ladder` and `Exit` pages were deleted on
2026-09-25: Trade's way in is the same scale-in and its way out the same scale-out. The
desk dropped the flip that day, so §5–6 are a record of why it was considered and what
was measured, not a plan.

**"The desk"** is the trader who owns this board and makes the decisions on it; a quote is
theirs. Claims are marked. **Decided** = the desk said so. **Derived** = arithmetic.
**Measured** = from data on disk, reproducible. **Open** = needs an answer before anything
is built.

---

## 0. Picking this up cold

- **Run it**: on the full board, `run_board.cmd` (http://127.0.0.1:8060). On a
  trade-board copy, `run_trade.cmd` (http://127.0.0.1:8065).
- **Read first**: [TRADE.md](TRADE.md) for what every control on the page does and why;
  this file for the reasoning behind the sizing.
- **Reproduce the measurements** (full board only; the scripts are not in a trade-board
  copy): `python scripts/measure_wobble_sr3.py` and `scripts/measure_wobble_zq.py`.
- **One sizing rule per page, no mode menus** (desk). Flat, ramp and target-average were
  built and deleted for being unprincipled; anything new needs an actual argument.

---

## 1. The identity everything rests on

**Derived, built.** Stopped out of a position built at levels `pᵢ` with `qᵢ` lots:

```
loss  =  Σ qᵢ · |pᵢ − stop| · $/bp
```

Two consequences that keep reappearing:

- **Lots are not equally expensive.** One entered far from the stop consumes more budget
  than one near it. That is why "borrowing lots from higher levels" is exact rather than
  a figure of speech, and why skipping a far level frees disproportionately more size.
- **A lot's cost is its distance from the stop.** Section 4 is this same sentence with
  the stop swapped for the target.

---

## 2. What is built

### Scaling in — Trade's way in (the `Ladder` page until 2026-09-25)

- **Deleted as a page** on 2026-09-25: Trade did everything it did, and its fill-depth
  P&L was valued at the target — the overstated figure below. The arithmetic stays in
  `ladder.plan`, which Trade's way in runs.
- **Equal risk.** Every level puts the same dollars at risk, so an even split of dollars
  buys uneven lots: 21.0 → 19.0 stop on $5k gives 25 / 33 / 50 / 101.
- **Stop and target are drag flags** — left button since 2026-10-09 (desk); it was the
  right, the gesture on the platform the desk trades, until then.
- **Default skips are derived, not stored**, so moving the entry or stop re-picks them.
  The Ladder page pulled both end rungs; Trade pulls only the rung above the stop.
- **Filled per rung** (was `Held`) — type what you already have. On a working rung it is a **fill
  against that rung** and the rung shows what is left; anywhere else it is a prior
  position, charged against the same budget. Overfill comes out of the rungs not yet
  filled (2026-09-24; TRADE.md has the worked numbers).
- **Max loss is a hard cap** (desk, 2026-09-29). Filled plus still to work never goes over
  it. Whatever overfill the empty rungs cannot absorb comes off what is left on the
  rungs nearest the stop, starting with the one closest to the stop.
- **A peak on equal risk** (desk, 2026-09-27). Click a rung in the gold-dot column (far
  right) and the dollars at risk follow a bell curve centred there instead of lying
  flat: a rung one width from the peak takes half the peak's risk. Width is one control,
  **Off · Broad · Medium · Narrow**, a half, a third or a fifth of the entry-to-stop
  distance — a share, so a name means the same shape on every trade. Off is equal risk
  exactly, with the dot kept but dimmed. The ends are not set; they fall where the curve
  puts them, so an off-centre peak is steeper on its short side. Why a hump: the risk worth
  putting on a rung is roughly the chance it trades there times how good the price is,
  and the first falls toward the stop while the second rises. On the 16 → 20.5 SR3 short,
  $4k, peak 18.0 Medium: 4/5/6/7/8/10/13/20 lots become 2/3/6/9/12/13/14/14; filled to 18.0
  goes from 30 lots at R:R 0.70 to 32 at 0.83, and the full fill barely moves (1.60 → 1.59).
  `ladder.peak_weights`, `ladder.PEAK_WIDTHS`.
- **A rung the peak sizes to 0 lots is a skip** (desk, 2026-09-27): derived, re-picked on
  every change like the rung above the stop, its share re-split by the curve. Click it to
  put it back (live, at whatever it gets); click again to let it go. Only with the peak on,
  so Off is the page exactly as before. No 1-lot minimum — the desk would not trade a
  rung prescribed one lot anyway.
- **Output is a fill-depth table**, not one R:R number: with a scale-in, R:R is path
  dependent and a single figure has to assume the full fill, the case you least expect.
- Market line dead centre, breakeven drawn at its true height.

### Scaling out — Trade's way out (the `Exit` page until 2026-09-25)

- **Deleted as a page** on 2026-09-25, with the flip it carried — the desk: "flip is
  trash". The arithmetic stays in `exits.plan`, which Trade's way out runs.
- **Equal regret**, section 4.
- **`Sold` column** (2026-09-23) — type what you have sold, rung by rung. What is still on
  is re-split by equal regret across the rungs **ahead of the furthest sale**; the rungs
  behind it are drawn as passed, with no size and no click. The mirror of `Filled`.
- **Skips survive the mark moving.** They used to be wiped whenever the bid/ask was
  retyped; they are now filtered, exactly as on the scale-in.
- **A peak on equal regret** (desk, 2026-09-29): the way in's peak mirrored, §4. Its own
  blue dot and PEAK OUT control; OUT P&L became OUT REGRET, the quantity it bends.
- **Gone with the page:** the `Took` column (Trade's `Filled` does the job), the flip fields
  and the `OFF`/`ON` flags, the `FREE` chip, and the default pull of the rung next to
  flat-by.

### The cut — Trade's way out at a loss (2026-09-30)

- **OUT BY**, past the stop: the level you are fully out by. The stop stays the level the
  trade most likely will not go beyond, where the way in stops adding.
- **Equal loss** from one rung past the stop through OUT BY. Max loss covers the trade all
  the way there, so the way in is sized to the cut's average. §9.

### `Trade` — both halves on one ladder

- **Built as a third page, not a replacement.** It has since replaced both `Ladder` and
  `Exit`, deleted 2026-09-25, and is the only ladder page.
- **No new arithmetic**: `ladder.plan` in, `exits.plan` out, equal risk and equal regret
  exactly as on the pages they came from. The page is the join between them.
- **The join is the fill depth.** A scale-in produces a position *per depth*, so the exit
  half sizes whichever row of the fill-depth table you click. Full fill by default.
- **No flipping.** Left out deliberately at first — it moves no lots through either
  ladder — and then dropped by the desk on 2026-09-25.
- **Four draggable levels** — stop, entry, first exit, target.
- **The first exit is bounded by the AVERAGE, not the entry.** Scaling a long down pulls
  the average below the entry, so the band between them is already profit and refusing it
  was wrong. Entry 21.0 / stop 19.0 / $5,000 fills 167 at 20.198, so 20.5 is a real exit
  worth $68 on 9 lots. At depth 0 the average is the entry and the old behaviour stands.
  Consequence: the two halves can share a rung — add on the way down, sell on the way back
  up — so skips are two stores and the position is two columns (`Pos` in, `Left` out).
- **Answers the two questions it was built for**: how a loss budget is spread across
  levels when you already hold some lots (`In`, `Risk $`, and the fill-depth table), and
  how to come out of whatever that left you holding (`Out` and the reversal table).
- **The fill-depth table's P&L is what the way out BANKS** (2026-09-23), one exit plan
  per row. It used to value the whole position at the target, which the exit ladder never
  sells at — the target is the flat-by boundary — so it overstated the reward by about
  half: full fill printed **$15,875, R:R 3.17** against the **$10,762, 2.15** the exit
  beside it banked. The deleted Ladder page valued at its target; it had no exit ladder.
- **`Sold` sits outside `Out`**, as `Filled` sits outside `In`. Sold lots come off `Filled`
  at its average, and what they banked is **booked P&L**: it is on every loss and P&L
  figure, and it never goes back into the budget.
- **A sale never changes the way in. Decided 2026-10-08** (desk: "max loss only ever
  covers open risk"). Max loss is spent once: neither the profit a sale banks nor the risk
  the sold lots stop carrying is handed back, so the way in is sized and capped exactly as
  if nothing were sold. *History:* until 2026-10-08 both were credited, my call and not
  the desk's, and a sale put lots back to work on rungs already filled (filled 33 at 21.0
  and 44 at 20.5, 20 sold at 21.5: 9 and 11 lots reappeared on the filled rungs and 20.0
  went 67 → 83). The desk: "this was irritating me till now".
- **Round trips are not Sold. Decided 2026-10-08.** Lots sold to be bought back — trading
  around the position, not exiting — are recorded by taking them off `Filled` at the rung
  you mean to buy them back at, which puts that rung back to work. Taking lots off Filled
  at a rung is the page's way of saying they were sold AT that rung, so it forgets the
  round trip's profit — lots × (price sold − that rung) × $/bp — and states the loss at the
  stop that much too high: the safe side of max loss. Sold would get the money right but
  passes the exit rungs behind the sale. The profit is booked P&L and never lets the
  trade risk more. Not on the page, by the desk's choice (§5: flipping stays off it); a
  Rebuy column is in reserve (§7).
- **Default skips** (desk, 2026-09-24): going in, only the rung right above the stop is
  pulled (the entry rung is worked); coming out, nothing is pulled. The deleted pages
  differed: `Ladder` pulled both ends, `Exit` the rung next to flat-by.

### P&L from settle — a reference (2026-10-01)

- **The settle box** shows each whole-trade P&L figure again, measured from settle
  instead of entry, because the statement marks the book there daily. It is the entry
  figure less what the statement already shows. Nothing is sized on it. TRADE.md has
  the details.

### Shared

- **Tick values (desk-supplied; the repo does not cite contract specs):** 0.5bp grid,
  SR3 $25.00/bp = $12.50/tick, ZQ $41.67/bp = $20.83/tick.
- **Level fields are TEXT inputs, not number inputs.** A number input paints a negative
  *value* in accounting style, so a stop of −10 appeared as `(10)`. Placeholders escape
  it, which is why stand-ins looked right and typed levels did not. Do not change these
  back.
- `assets/ladder-drag.js` is generic: it reads `data-input`, `data-lo` and `data-hi` off
  whichever flag was grabbed. The server renders the legal range rather than the script
  re-deriving the rules. It had a `data-offset` for the flip band's far edge, which wrote
  the near one; it went with the flip.

---

## 3. What scaling out is

**Decided.** Not the scale-in with the signs flipped, and not only about protecting a
trade:

> Even if we weren't flipping, we'd do something similar to scaling in, because we don't
> know which level it might revert from. Same delicate balance: exiting lots while trying
> to exit at the best average.

| scaling in | scaling out |
|---|---|
| entry | first exit |
| stop — where you stop adding | flat-by — where you are fully out |
| max loss — the budget to spread | position — the lots to spread |
| **best average entry** | **best average exit** |
| don't know how far it runs against you | don't know where it reverts from |

**The one place it is not a pure mirror. Derived.** A rung you never reach on the way in
leaves you light and onside. One you never reach on the way out leaves you heavy and it
is coming back. Light-and-winning versus heavy-and-giving-back.

---

## 4. Equal regret — the exit sizing rule

**Decided and built.** The exact dual of equal risk:

```
scaling in    a lot costs  |p − stop|     what it loses if stopped
scaling out   a lot costs  |target − p|   what it GIVES UP if the move runs on

              q  ∝  1 / |target − p|
```

- Lots rise as you work further out. 21.0 out to a 23.0 target on 200 lots gives
  **24 / 32 / 48 / 96** — the same proportions as 25/33/50/101 read backwards.
- **`flat by` is a boundary, not a rung.** A lot sold at the target forgoes nothing and
  would take unbounded size, exactly as the scale-in excludes its stop.
- **Lots sum to the position exactly.** Equality, not a ceiling — anything left over is a
  lot you forgot to sell. The one place the arithmetic differs from the scale-in.
- **History — the rung next to flat-by was pulled by default** on the Exit page
  (2026-09-23). **Trade does not pull it: coming out, nothing is pulled by default**
  (desk, 2026-09-24; §2). The reasoning stays for the record. It mirrored the scale-in
  pulling the rung next to its stop, and for the same reason: equal regret
  gives that rung the biggest lot on the ladder — 68 of 167 on a six-rung exit, 11 at the
  first. Held off below three rungs; click to put it back; `Clear skips` puts it back.
  **What it costs, measured:** that rung is also the best price, so the average falls.
  21.0 → 23.0 on 200 lots: 24/32/48/96 averaging 22.04 and banking $5,200 becomes
  46/62/92 averaging 21.615 and banking $3,075. The Trade example (167 at 20.198): 22.775
  → 22.278, $10,762 → $8,687. It buys a lighter last rung and a heavier first one; it is
  not free, and on a short ladder (four rungs) the pull is a quarter of the ladder.
- **`if runs` rides to flat-by**, not to the last rung (fixed 2026-09-23). It used to stop
  a rung short, so the `now` row disagreed with the page's own "holding all of it to X"
  figure.
- **It buys** a better average: 22.04 against 21.75 for an even split. **It costs**
  back-loading: 56 of 200 sold by 21.5 where flat would have sold 100.
- **Risk-free is a marker (`FREE`), not the rule.** An earlier version sized around it,
  selling ~half the position at the first rung — the worst average exit available. That
  was wrong and is gone.

- **A peak** (desk, 2026-09-29, built). The way in's kernel on the regret instead of the
  risk: each rung's share of the upside forgone is `2^−((p − peak)/w)²`, divided by the
  regret per lot to give lots, with `w` a half, a third or a fifth of first exit to
  target. Equal regret is the infinite width. Skips re-split in proportion.
- **The peak is not free here.** Going in, the budget is fixed and the peak only moves
  dollars. Coming out, the lots are fixed, so total regret — `position × |target − avg
  out|` — changes with the peak, and each dollar of it is average given up. Long 200,
  21.0 out to 25.0, Medium:

  | | lots, 21.0 → 24.5 | avg out | sold by 22.0 |
  |---|---|---|---|
  | equal regret | 9 / 10 / 12 / 15 / 18 / 25 / 37 / 74 | 23.54 | 31 |
  | peak 23.0 | 3 / 7 / 13 / 22 / 30 / 36 / 40 / 49 | 23.46 | 23 |
  | peak 22.0 | 16 / 24 / 31 / 34 / 32 / 26 / 20 / 17 | 22.71 | 71 |

  A mid-ladder peak thins the tail for 0.08 of average; an early one front-loads the
  exit for 0.83. The hump is in the regret dollars, not the lots — dividing by regret
  per lot still leans lots toward the target unless the peak sits early. It is the first
  control aimed at the back-loading above.

*History: flat was proposed, the desk pushed back that lots should rise as you work out
the way they do scaling in, and was right.*

---

## 5. Flipping

**Dropped, 2026-09-25.** The desk: "flip is trash". The Exit page that carried it was
deleted and nothing on the board flips now. This section and §6 are kept as the record
of why it was considered and what the data said; do not rebuild it unless the desk
raises it again.

**Decided at the time.** The desk flips 20–30% of a position around a core:

> We book a few lots early so a reversion pays us something, and we keep the ability to
> re-add lower. Otherwise it does up and down for months and someone flipping 20–40% has
> made more P&L than someone sitting waiting for a target.

- **Core catches the move; the flip pays the rent while you wait.**
- **The split is adjustable and changes discretionarily** with market conditions.
  Currently fixed on the page.
- **The band is never the same twice** — it is named per trade (6.5–7.0, sometimes
  6.0–7.5), not configured globally.
- **They sell both above and below the average.** The average is sunk; it is not a
  boundary and must never be a validation rule.
- **Flipping is used to recoup while underwater**, and both because the flip P&L is
  *realised* while the core's loss is unrealised, and because it smooths the path.

### 5.1 The hurdle

**Derived.** Worked with the desk's own trade — short 60 ZQ at 6.91, stop 9.5, target
5.25, flip 20, band 6.5–7.0:

- One round trip banks 0.5bp on 20 lots = **$417**.
- Bought 20 back at 6.5 and it runs to 5.25: you missed 1.25bp on 20 = **$1,042**.
- **Break-even = 1,042 ÷ 417 = 2.5 round trips.**

```
break-even cycles  =  distance from your flip level to the target  ÷  band width
```

- **The lot count cancels.** Flip 30 instead of 20 and both numbers scale; still 2.5.
  So the 20–30% cap costs nothing in edge — it only sets the size of the prize.
- **So does the tick value.** The hurdle never depends on the instrument.
- **What the cap does control** is how much of the move you guarantee. Core of 40 at
  1.66bp locks in **$2,767** of the $4,150 whatever the flip does.

### 5.2 Volatility is the wrong conditioner

**Derived.** On a random walk, path grows with time and net move with its square root, so
`path / net` rises with **holding period** and volatility cancels out entirely — it
scales the payoff and the opportunity cost equally.

- **The desk's instinct still has a valid basis**, just a different one: a more volatile
  structure tags resting orders more often, and flipping only pays if you rest rather
  than cross. That is a fill-rate argument, not a reversion one.
- **The real edge is mean reversion** — and the desk said it better than the algebra:
  structures they know come back to their mean, that the market is irrationally pricing
  at an extreme. Trailing stop for trending instruments, flip for reverting ones.

### 5.3 The accounting trap

**Derived.** Long 100 at 20.0, sell 30 at 19.0, buy back at 18.5:

- Realised books **−$750** (sold a bp below the average, thirty times).
- Average falls to 19.55.
- You are **+$375** better off at every future price — exactly `30 × 0.5bp × $25`.

**The realised line says −$750 while you are +$375.** Half the gain hides in the lowered
average. Any page reporting one combined P&L will look like it loses money every time it
works. *The desk's framing — "we're improving our average" — is the same number from the
other side; noted deliberately, not built.*

### 5.4 Flipping helps most when you are wrong

**Derived.**

- **Round-tripped: pure addition.** You end holding what you would have held anyway, so
  the only difference is what you banked. Direction irrelevant.
- **Still short the flip into a decline: the loss is cut.** Long 100 at 20.0, sell 30 at
  19.5, it goes to 18.0 — holding all is −200bp·lots, flipped −155.
- **The only losing path is a sharp favourable runaway you never buy back into.**

**The trap in "recoup":** the arithmetic justifies flipping a *fixed* allowance. It says
nothing about enlarging it because you are down.

---

## 6. Measurements

**Measured**, 63-day windows, roll neutralised, idealised execution (no costs, no queue).
Scripts: `scripts/measure_wobble_sr3.py`, `scripts/measure_wobble_zq.py`.

Counted **completed round trips**, not total wandering — a first cut used `path / 2`,
which assumes every wiggle is capturable, and it is not.

### SR3 structures

| band | trips | banked bp/lot | net move | flip wins |
|---|---|---|---|---|
| 0.5bp | 15 | 7.5 | 4.0 | 63% |
| **1.0bp** | **12** | **12.0** | **4.0** | **79%** |
| 2.0bp | 7 | 14.0 | 4.0 | 76% |

**Tenor — the strongest result, and it confirms the desk's compression point:**

| generic | trips | net | wins |
|---|---|---|---|
| n=1 | 13 | 22.0 | 30% |
| n=8 | 12 | 4.0 | 87% |
| n=12 | 12 | 2.0 | 99% |

The wandering is flat across tenor; the net travel collapses. Flipping gets monotonically
better further out.

**By structure (1.0bp):** 3mo double fly 99%, 3mo fly 93%, 6mo fly 77%, 12mo spread 52%.
Differences beat levels.

### ZQ meeting structures

Unit is a **specific pair over its whole life** (Sep'26/Oct'26), which is roll-free by
construction — the anchored series re-points four times a year and those jumps are not
tradeable.

| band | trips | banked | net | wins |
|---|---|---|---|---|
| **0.5bp** | **10** | **5.0** | **2.06** | **85%** |
| 1.0bp | 5 | 5.0 | 2.06 | 73% |
| 2.0bp | 1 | 2.0 | 2.06 | 41% |

**By type (1.0bp):** meeting spreads 86–88%, outright meetings 57%. Same pattern.

### What the measurements changed

- **The band does NOT cancel in practice.** Trips do not scale as `1/width`, so the
  idealised "width is only a cost question" was wrong.
- **The right width is proportional to amplitude** — roughly a quarter of the typical net
  move. SR3 wants 1–2bp, ZQ meetings want 0.5bp (one tick).
- **Daily closes badly undercount tight bands** — you cannot see more than ~31 reversals
  in 63 observations. The 0.5bp SR3 row is a sampling artifact; these are a conservative
  floor. Intraday data would settle it.
- **The best flip candidates are the least liquid** (SR3 n=10–12), which is exactly where
  resting fills are hardest. Unresolved tension.
- **ZQ tenor test inconclusive** — each pair traverses every tenor during its own life,
  so bucketing by distance mixes the same pairs across rows.

### Against the desk's own trade

Hurdle 2.5 cycles; ZQ median at a 0.5bp band is **10 per quarter**. Cleared four times
over — about **$4,167 a quarter** on 20 flip lots against **$1,042** forgone. Their
6.5–7.0 band is the width the data would have picked.

---

## 7. Open

1. ~~**Merge `Exit` into `Ladder`?**~~ **Settled 2026-09-25.** `Trade` carries the entry
   and exit halves on one ladder, and both older pages were deleted. The flip, the one
   thing it did not carry, was dropped by the desk rather than moved.
2. ~~**The flip hurdle still measures from the average.**~~ **Fixed 2026-09-23.** The
   hurdle is now `|flat by − OFF edge| / band`, and the forgone dollars use the same
   distance. Note the edge: this item used to say `ON`, which was a slip — §5.1's own
   worked answer covers 20 at **6.5** and misses 6.5 → 5.25, and 6.5 is where the
   allowance comes **off** (`OFF`, per `_flip_band`). `ON` (7.0) would give 3.5, not 2.5.
   On the desk's trade the formula now gives 2.5 exactly.
3. **Should the page know which structure you're trading?** It is instrument-agnostic
   today. Knowing it (a 6mo fly at n=5, a Q vs NQ at buffer 2) would let it show the
   measured benchmark next to the live hurdle — the piece that replaces feel. Needs a
   picker on a page the desk wants simpler.
4. ~~**Discretionary core/flip**~~ — moot since the flip was dropped (2026-09-25).
5. ~~**Cumulative round-trip P&L**~~ — moot since the flip was dropped. A trade log is
   still the missing piece for `Sold` (§8).
6. **Intraday data** for the tight-band undercount — moot for flipping; still the way to
   settle any band-width measurement.
7. **A Rebuy column — in reserve** (desk, 2026-10-08: "keep it in reserve and add to
   future plan implementation"). For round trips (§2): type the lots at the rung sold, click
   the rung to buy them back at; the page takes them off the position, books the profit,
   works them at the rebuy rung and leaves the exit ladder alone. Not built. Until then,
   round trips go through Filled.

---

## 8. Known gaps in what exists

- The stop doubles as the last level you add at on the scale-in, so you cannot stop
  adding at 20.0 and leave the stop at 18.0. This also flatters equal risk, which loads
  size nearest the stop. **Mostly answered by OUT BY (§9):** the stop is where adding
  ends, and the risk is measured to the cut's average past it.
- No per-level size override — skip and the two peaks are the only controls.
- **`exits.plan` still takes `carried`**, the flip lots counted on the stop side. Nothing
  passes it since the Exit page went; it defaults to 0 and is harmless, but it is dead.
- ~~The ladder jumps a row when the title grows.~~ Fixed 2026-09-24: on `Trade` the title
  has a fixed two-line box and the caption its own line, so a longer title no longer
  pushes the rungs down under the cursor.
- **Sold is not a trade log.** It says what has gone out, not in what order; "ahead" is
  measured from the furthest sale, so a sale at 21.0 followed by one at 20.5 on a pull-back
  still counts 20.5 as behind you.
- No fill probability by level. The excursion data measured in section 6 is the input.
- **Touch is not fill.** Nothing on the page knows a level sits behind a
  five-thousand-lot queue.
- The drag leans on driving a React input from outside — a documented workaround, not an
  API. Works on Dash 4.2; a Dash upgrade could break it silently. The typed field stays
  the source of truth, so a break costs the drag, not the ladder.

---

## 9. The cut — out past the stop

**Decided 2026-09-30.** The desk:

> stop right now refers to the level it most likely not go beyond … if it is going
> beyond here i would want to start exiting lots because i can only devote so much pnl
> to a particular trade or to a particular viewpoint

- **The stop keeps its name and its job on the way in.** It is the level the trade most
  likely will not go beyond, where adding ends.
- **A new level, OUT BY, is where you are fully out.** The desk picked the names (keep
  STOP, add OUT BY) and where the cut's lots show (in the Out column).
- **The cut runs from one rung past the stop through OUT BY.** In the desk's example, 19.0
  is the stop and the cuts are at 18.5 and 18.0, with OUT BY at 18.0.
- **Max loss covers the whole trade, OUT BY included.** It is what one trade may cost. The
  cut spends part of it, so the way in is sized to fit.
- **The method was left to the page** ("the most optimal way is figured out by whatever
  method"): equal loss, below.
- **Nothing was measured**, at the desk's word ("measure nothing").
- **Before the build,** a proposal put the first cut *at* the stop. The desk's version
  starts a rung past it, which is deeper and costs more size. The numbers below are the
  desk's version.

### 9.1 The identity

**Derived.** Take a book of `n` lots at `A`, cut `cᵢ` at `xᵢ`:

```
loss  =  Σ cᵢ · |A − xᵢ| · $/bp  =  n · |A − c̄| · $/bp,      c̄ = Σ cᵢ·xᵢ / n
```

- **A cut is a stop at its own average.** For its loss, cutting across the rungs is the
  same as one stop at `c̄`.
- **So §1 holds with the stop replaced by `c̄`.** The way in is equal risk measured to
  `c̄` (`ladder.plan`'s `risk_to`). Against a plan with no cut, lots in scale by
  `(A − stop) / (A − c̄)`.

### 9.2 Equal loss

**Built.** `qᵢ ∝ 1 / |A − xᵢ|`. Every cut rung takes the same dollars of loss, the way
every rung in puts the same dollars at risk. Lots get smaller deeper in the cut, because a
lot cut deeper loses more.

- **Why not even.** There is no argument for it, and it puts the most loss on the deepest
  rung.
- **Why not back-loaded.** Cutting most at the far end holds most of the position into the
  move most likely to be real. It also costs the most size.
- **Measured from the average**, so each depth gets its own split.
- **The way in is sized to the full fill's `c̄`.** `c̄` depends on the average, which
  depends on the lots, so `cuts.fit_in` iterates. It settles in a few passes because `c̄`
  moves little with `A`.
- **Rounding goes toward the stop.** After flooring, the leftover lots go one each to the
  rungs nearest the stop. That keeps the whole lots' loss at or under the unrounded
  figure, which is the bound the tables report.
- **The cap is exact** (desk, 2026-09-29). After the iteration, the full fill cut through
  OUT BY is checked against max loss, on the book as if nothing were sold (2026-10-08:
  cuts and sales give nothing back). Any excess comes off the way in's budget.
- **The full fill is usually the worst depth, so every depth is checked** (2026-10-04).
  A book's loss is `n` times the harmonic mean of `A − xᵢ`, and every lot added only
  raises that -- while `A` stays clear of the band. Fills typed past the stop can put a
  shallow book's average at or past a cut rung, where equal loss means nothing and the
  cut splits evenly; that depth can lose more than the full fill (an audit case: $1,662.50
  at depth 7 on a $1,547 cap, full fill $1,488). So after the full fill fits, every
  depth is checked, and if one is over, halving finds the largest budget at which all
  fit. A filled book over max loss on its own adds nothing.
- **A cut already made is typed in Sold.** What is still on is re-split over the rungs
  beyond the furthest cut. With every rung passed, what is left measures to OUT BY.

### 9.3 What it costs

**Measured on the page's own arithmetic.** SR3 long, 21.0 → 19.0, $5,000 max loss, with
the rung above the stop pulled:

| OUT BY | cut at | lots in (21.0 / 20.5 / 20.0) | cut lots | c̄ | loss at worst |
|---|---|---|---|---|---|
| none | 19.0, all | 33 / 44 / 67 = 144 | 144 | 19.00 | $4,975 |
| 18.5 | 18.5 | 27 / 33 / 44 = 104 | 104 | 18.50 | $4,988 |
| 18.0 | 18.5, 18.0 | 24 / 30 / 39 = 93 | 52 / 41 | 18.28 | $4,977 |
| 17.0 | 18.5 … 17.0 | 21 / 25 / 32 = 78 | 26 / 21 / 17 / 14 | 17.87 | $4,991 |

- **Holding lots past the stop costs lots on the way in.** One rung of cut costs 28% of
  the size, two rungs 35%, four 46%.
- **Most of it comes off the rung nearest the stop.** 20.0 was cheap only because the stop
  sat right under it.
- **Equal loss shows in the dollars, not the lots.** With OUT BY at 18.0, the two cut
  rungs lose $2,495 and $2,480.

### 9.4 Open

- **What a cut buys over one wider stop.** Hold the lots fixed and give both the same
  worst case. The cut and a single stop at `c̄` then differ only on a turn inside the cut:
  the cut is worse if it turns at the first rung, and better if it turns deeper.
  Measurable from the excursion data (daily closes undercount), and not measured, at the
  desk's word.
- **No skips and no peak on the cut.** Both would reuse the other halves' machinery.
- **The rung above the stop is still pulled by default going in.** That pull was there
  because equal risk gave it the biggest lot, being cheapest to the stop. Measured to the
  cut's average it is no longer the degenerate rung. It is left as the desk set it.
