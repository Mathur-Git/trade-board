# The Trade page: what everything on it does

The Trade sections of the STIR board's `docs/BOARD.md`, extracted on export. The why behind the sizing is in [SCALING.md](SCALING.md). Mentions of other pages (Ladder, Exit, Risk, Meeting Structures) are the full board's; they are not in this copy.

## Scaling in — the arithmetic under Trade's way in

This was first built as its own `Ladder` page. The page was deleted on 2026-09-25, once
the Trade page did everything it did. Its fill-depth P&L was also the overstated one,
valued at the target. What follows is the reasoning that still holds: Trade's way in runs
the same `ladder.plan`.

**One constraint.** Stopped out of a position built at levels `p_i` with `q_i` lots on
each, the loss is `Σ qᵢ·|pᵢ − stop|·$/bp`. Every mode is a different way of spending
that one budget.

**Which is why skipping a level re-allocates for free.** A lot entered far from the stop
consumes more budget than one entered near it, so dropping a far level frees
disproportionately more size than dropping a near one. On a 21.0→18.0 buy at $5k, flat,
six levels take 19 lots each; skip 21.0 and the remaining five take 27, but skip 18.5
and the remaining five take only 20. That asymmetry is the whole of "borrowing lots from
higher levels", and there is no rule implementing it — it falls out of the budget line.

**One sizing rule: equal risk.** Every level puts the same dollars at risk, not the same
lots. A lot is not equally expensive everywhere — one entered far from the stop costs
more of the budget than one near it — so an even split of dollars buys uneven lots,
fewer at the top and more toward the stop. On a 21.0 buy with a 19.0 stop and $5,000 the
ladder is 25 / 33 / 50 / 101, and the risk climbs in even steps of ~$1,250, which is the
signature of it.

Flat, ramp and target-average sizing were built and then deleted. They are not hidden
behind a flag; the code is gone.

**The output is a fill-depth table, not a risk-reward number.** With a scale-in, R:R is
path dependent: it turns on how far the market went before it reversed, which is the one
thing you do not know when you set the ladder. Any single figure has to assume the full
fill, which is the case you least expect. So there is one row per number of levels
filled, and the shallow rows — the likely ones — are where you find out whether the plan
is too light to be worth doing.

**Budget is spent once, not scraped.** Lots are whole, so a mode's ideal weights never
land exactly on the budget. Sizes are floored and topped up by largest remainder, one
pass. A second pass would spend the last few dollars, but only on the cheapest levels,
which are the ones nearest the stop — quietly turning a flat ladder into a bottom-heavy
one. The remainder is reported instead.

**Default skips are derived, not stored.** Only your explicit choices are kept, as `off`
(rungs you pulled) and `on` (default-pulled rungs you put back). So moving the entry or
the stop re-picks the defaults instead of leaving stale ones behind, and a click on a
default reads as "put this one back" rather than "pull it again". Which rungs are pulled
by default is a per-page choice — see [The Trade page](#the-trade-page).

**Markers have their own gutter**, never beside the price. A tag sharing the cell with
the number turns the price spine into a column of numbers-and-words, which is what a
ladder must not be. The blended average is drawn as a short red rule under the price
column — a level you look for is found faster as a line than read as a chip.

**The window is built around the market line, not the entry row**, with the same number
of rungs either side of it. The line sits directly above the entry when buying and
directly below it when selling — you scale away from it either way — so the entry row is
one rung off centre, and which way it is off is what tells you the side at a glance. The
window is fixed, so the line stays put as you move the entry; a range derived from the
stop and target would shift underneath you every time you touched one.

**Breakeven is drawn where it is, not on the nearest rung** — and measured from the
row's **centre**, because that is where the row's price is written. Measuring from the
top edge put an average a hair below 20.0 a hair *above* the "20.0" label: half a rung
out, and out in the wrong direction, which on a structure trading a few bp is worse than
not drawing it at all. So the line takes the nearest rung and offsets from its centre.
Exactly on a rung sits on the label; a quarter below sits on the row boundary, halfway
to the next label down. 19.957 lands at 58.6% of the 20.0 row — just below the label,
which is where 19.957 is.
It is an overlay running the full width of the price column, over the digits rather than
around them: a line that breaks around a number is a line you reassemble by eye.

**Levels are flags you RIGHT-drag.** Right button, not left, because that is the gesture
on the platform the desk trades on — moving a stop or a target that way is already in
everyone's hands, so it needs no teaching. The context menu is suppressed over the flags
and for a moment after a drop, since Chrome raises it on mousedown. The rung you would
drop on is outlined as you go, and on release the price is written into the matching
field, which is still typeable. Movement is **clamped** to a legal range the server
renders onto each flag — a stop stays on the losing side, a target on the winning side,
nothing leaves the drawn window — so drag past a limit and you park on it.

The drag lives in `assets/ladder-drag.js`, outside Dash's callback graph, because Dash
has no drag primitive. Writing the dropped price back needs the native value setter plus
an `input` event — assigning `.value` updates the DOM and React never hears it. That is a
workaround, not an API: if a Dash upgrade breaks it you lose the drag, not the ladder,
because the typed field remains the source of truth.

**Stand-in stop and target.** A missing stop works to four rungs from the entry and a
missing target to six, both on the side the trade implies and both well inside the
window — a target on the window's edge reads as the bottom of the ladder rather than a
level someone chose. The numbers appear **in their own boxes as greyed placeholders**, so
you can read what the ladder is using without it becoming a value you typed.

**The ladder never disappears.** It is the page, and it is how you see what is wrong with
the numbers — so a stop on the wrong side of the entry, a target that is not a profit, or
a missing field leaves the ladder on screen with a workable stand-in and a line saying
what to fix.

**A position already on is typed into the ladder, rung by rung.** The `Filled` column
takes lots at each price, because that is what anyone actually remembers: not the average
of a scaled-in position, but "40 at 20.5". Blending is lossless for risk — `Σ qᵢ(pᵢ −
stop)` equals `lots × (avg − stop)` identically — so per-level fills and a blended
average are the same number arrived at from opposite sides.

**Filled lots are one of two things** (desk, 2026-09-24):

- **On a rung the ladder is working, they are a FILL** against that rung. The rung shows
  what is **left** (16 planned, 7 filled: 9) and every other rung keeps its size. Before
  this, a fill was treated as a prior position and the rest re-split over every rung — 7
  at 1.0 made 1.0 take 13 more (20, over plan) and cut 0.5 from 26 to 20.
- **More than planned at a rung** is risk the plan did not budget for, so it comes out of
  the rungs with nothing filled yet. 40 at 20.5 against a planned 33 (21.0 → 19.0, $5,000)
  leaves 23 / 0 / 47 / 94 still to work.
- **Max loss is a hard cap** (desk, 2026-09-29): filled plus still to work never goes over
  it. Overfill used to come only out of rungs with nothing filled, so when every rung had
  a fill it was simply kept. ZQ short 6 → 9, $4,792, peak 7.5 Medium, with 20 / 8 / 26
  filled at 6.0 / 7.0 / 7.5: that fill already risks the whole $4,792, yet the page said
  take 15 more at 7.0 and 12 at 7.5, which is $6,792 if stopped. What the empty rungs
  cannot absorb now comes off what is left on the rungs nearest the stop, and here that
  leaves nothing to add. Skipping a rung with nothing left to work no longer changes
  anything else on the ladder.
- **Anywhere else** — a pulled rung, a price off the ladder — they are a position from
  before the plan, charged against the **same** budget, because `max loss` is what the
  trade may cost in total. The ladder is sized on what is left.

No extra column for it: `Filled` is what filled, the size column what is left, and the plan
is the two added together. The held position gets its own row at the top of the
fill-depth table — where you stand before the ladder acts — and every average below it is
blended, so what you read is the book, not the increment. Filled rungs outside the visible
window keep counting.

**Touch is not fill.** There is no depth feed behind the ladder, so the platform's Bids
and Asks columns carry our own size here. Nothing on the page knows that a level sits
behind a five-thousand-lot queue. That is the first thing to add.

**Ticks.** 0.5bp grid. SR3 is $25.00/bp so $12.50/tick; ZQ is 5/3 of that, $41.67/bp
and $20.83/tick. Desk-supplied — note the repo does not cite contract specs.

Known gaps, in the order they bite: the stop doubles as the last level you add at, so
you cannot stop adding at 20.0 and leave the stop at 18.0 — which also makes `Equal risk`
flattering, since it loads size nearest the stop. OUT BY (2026-09-30) answers most of
this: the stop is then where adding ends, and the risk is measured to the cut's average
past it. No per-level size override, only skip.
No fill probability by level, though the excursion distribution the Moves page measured
(retired 2026-10-06, see [RETIRED_PAGES.md](RETIRED_PAGES.md)) is the input for it. No queue awareness, and no link to the live structure
price.

## Scaling out — the arithmetic under Trade's way out

This was first built as its own `Exit` page, beside a flip model. The page was deleted
on 2026-09-25. The desk dropped the flip ("flip is trash"), and Trade already did the
rest. What follows is the reasoning that still holds: Trade's way out runs the same
`exits.plan`. The flip's reasoning and measurements stay in
[SCALING.md](SCALING.md) §5–6 as a record, not a plan.

**It is not the scale-in with the signs flipped**, which is why it is a separate module
(`lib/exits.py`).

**The constraint changes shape.** Going in, size is the unknown: you choose how many lots
to commit against a loss budget, and the constraint is an inequality — spend at most
`max loss`. Coming out, size is settled. There is no budget, and the constraint is an
equality: the lots sold across the rungs must add up to the position. It is a partition,
not an allocation, which is why equal-risk weighting has nothing to say here.

**One rule: equal regret** -- the exact dual of the scale-in's equal risk, with the stop
swapped for the target.

```
scaling in    a lot costs  |p - stop|     what it loses if stopped
scaling out   a lot costs  |target - p|   what it GIVES UP if the move runs on

                q  proportional to  1 / |target - p|
```

Lots therefore rise as you work further out: a lot sold near the target forgoes almost
nothing, one sold near your entry forgoes the whole move. It produces very nearly the
same shape as equal risk read backwards -- 21.0 down to a 19.0 stop on $5k gives
25/33/50/101, and 21.0 out to a 23.0 target on 200 lots gives **24/32/48/96**.

It inherits the same degeneracy and takes the same fix. A lot sold AT the target forgoes
nothing and would take unbounded size, so **the target is the boundary beyond the final
rung, not a rung itself** -- exactly as the scale-in excludes its stop.

**What it buys and what it costs.** A better average exit if you get there: 22.04 against
21.75 for an even split. The cost is that it is back-loaded, so a reversal finds you
heavier -- 56 of 200 sold by 21.5 where flat would have sold 100. That is the real
asymmetry between the two sides: a rung you never reach on the way in leaves you light
and onside, one you never reach on the way out leaves you heavy and it is coming back.

**The rung next to the target was pulled by default on the Exit page** (2026-09-23),
because equal regret gives it the biggest lot on the ladder. Trade pulls nothing coming
out (desk, 2026-09-24). What that pull cost in average is in SCALING §4. **Skips are
filtered, not wiped**, when the rungs move.

**Risk-free is a marker, not the rule.** The rung at which realised profit first covers
what the remainder gives back at the stop is worth seeing; it is the row the reversal
table highlights. It is not worth sizing around: doing so sells about half the position
at the first rung, which is the worst average exit available. An earlier version of the
Exit page did exactly that.

**Lots sum to the position exactly.** Equality, not a ceiling -- anything left over is a
lot you forgot to sell. That is the one place the arithmetic differs from the scale-in,
where overshooting the budget is the error to avoid and undershooting is merely untidy.

**Partial sales do not move your average.** Selling realises profit; it does not change
the cost basis. So the remainder's breakeven is the entry average the whole way out.

**You type what you have sold.** What it banks is measured against the held average, and
what is still on is re-split by equal regret across the rungs **ahead of the furthest
sale**. The rungs behind it are drawn as passed — dimmed, no size, no click — because the
market has been through them. The plan re-sizes to what you have actually done.

**The reversal table** is the fill-depth table's opposite: one row per rung reached,
showing what is banked, what is still carried, what the whole trade is worth **if it
stops from there**, and what it is worth **if the rest runs to the target**.

## The Trade page

Both halves of one trade on one ladder, and now the only ladder page. Built beside the
`Ladder` and `Exit` pages because the desk thinks about getting in and getting out
together, and two pages meant retyping the position and carrying an average across on
paper. Both were deleted on 2026-09-25. The way in and the way out still run on their
arithmetic: [scaling in](#scaling-in--the-arithmetic-under-trades-way-in) and
[scaling out](#scaling-out--the-arithmetic-under-trades-way-out).

**No new arithmetic.** `ladder.plan` sizes the way in against a loss budget, `exits.plan`
partitions the way out, and this page is the join. Equal risk in, equal regret out, both
exactly as the pages they came from.

**No flipping.** The desk dropped the flip on 2026-09-25, and the Exit page that carried
it went with it.

**The join is the fill depth.** A scale-in does not produce one position, it produces a
position per depth — which is the entire argument for the fill-depth table. So the exit
half sizes whichever depth you pick: click a row of `if it fills this far` and the way
out, the `Out` column, the reversal table and the red average line all re-size to the
position that row leaves you holding. The full fill is the default and the shallow rows
are the ones worth reading.

**The `In` column does not change when you pick a depth**, and should not: the plan is the
plan. Only what you would be selling changes, because only the position changes.

**Four levels define the trade** — stop, entry, first exit, target — and all four
right-drag. A fifth, OUT BY, is optional: the level past the stop you are fully out by
(see [the cut](#trade-the-cut-past-the-stop)). The averages fall out of the sizing, so
they do not drag.

**The first exit is bounded by the average, not by the entry.** Scaling a long *down*
pulls the average below the entry, so everything between the two is already profit and
there is no reason to refuse it: you work out as soon as the book is onside, which is
often well before the market is back where you started. Entry 21.0, stop 19.0, $5,000 →
full fill is 167 lots at 20.198, so a first exit at 20.5 is real money — 9 lots there bank
$68. At depth 0 the average *is* the entry, so nothing changes there. The entry is
therefore not capped by the first exit either; the two are free to cross. What stays
fixed: the stop on the losing side of the entry, and the target beyond the first exit,
because the target is the boundary you are flat by.

**Which means the two halves can share a rung.** A long that adds at 20.5 on the way down
may also sell at 20.5 on the way back up. That is one plan across price *and time*, and it
is exactly what the two size columns already say — but it costs two mechanics:

- **Two skip stores**, one per half. A single store keyed by price could not say which of
  the two you clicked. Defaults (desk, 2026-09-24): the way in pulls **only the rung right
  above the stop** — the entry rung is worked — and the way out pulls **nothing**.
- **Two position columns.** `Pos` is what has accumulated at that price on the way in,
  `Left` what remains after selling at it on the way out. One column served both while
  they could not collide and is wrong now.

**`In` and `Out` stay two columns** regardless — a size in the wrong one would read as the
opposite trade.

**A shared rung is not struck through.** The price is struck only when the rung carries no
size at all, since one half skipped and the other live is a rung you still work.

**The bars follow the side you would work it.** A long adds on the bid and sells on the
ask; a short adds on the offer and covers on the bid. So the two halves land on opposite
sides of the spine without being told to.

**The fill-depth table's P&L is what the way out banks** from that depth — each row is
priced through its own exit plan (2026-09-23). It used to value the whole position at the
target, which the exit ladder never sells at, and overstated the reward by about half.

**`Sold` sits outside `Out`**, as `Filled` sits outside `In`. Sold lots come off `Filled` at its
average, the rungs behind the furthest sale are passed, and what the sales banked is
booked P&L, on every loss and P&L figure. **A sale never changes the way in** (desk,
2026-10-08: "max loss only ever covers open risk"): neither its profit nor the risk the
sold lots stop carrying goes back into the budget, so the rungs stay exactly as they were
before the sale. Until then both were credited, and a sale put lots back to work on
filled rungs. **Round trips** — lots sold to be bought back — are not Sold: take them off
Filled at the rung you will buy them back at ([SCALING.md](SCALING.md) §2).
**Never more lots than were filled** (desk, 2026-10-04): Sold typed past Filled counts
only the filled lots, the least profitable sales first — a cut at a loss before any
profit — so what is banked can only be understated. 10
filled at 21.0 with 30 typed sold at 22.5 banks $375, not $1,125. The boxes keep what you
typed, and the title says "30 sold is more than the 10 filled · counting 10".

**The mark loads it** — the bid when you are long, the ask when you are short, the price
you could get out at — and the window centres on it. The entry stands in as the mark until
you type one: until you say otherwise you are getting in where the market is.

**The panel is capped and centred**, unlike the full-width pages. Left as `1fr` the right
column took the whole monitor — 977px on a 1600px screen — and stretched an eleven-column
table of short numbers across it, putting a hand's width between a label and its figure.
Both columns are capped and the card is capped to match, so it ends where the content ends.

Note that `#trade-wrap .lad-grid` outranks the plain `.lad-grid` inside the 1100px
stacking media query — media queries add no specificity — so it is restated there. Without
that, the narrow layout silently stopped applying to the page that needs it most.

## Trade: the levels table and the two marker columns

Added 2026-09-24, on Trade and the since-deleted Exit page.

**The levels are a table, IN beside OUT.** Each level sits next to its partner — `start`
is the entry beside the first exit, `end` the stop beside the target —
and the two averages they produce are the row underneath: red for the average in, green
for the average out. Both are **shown, not typed**; the entry average comes from the fills,
the exit average from the sizing and what you have sold. Max loss follows.

**Under a box, the value the ladder is using — only when it replaced yours.** A first exit
typed at 20.0 on a 20.198 average is not a profit, so the box keeps your 20.0 and the line
says "using 21". An empty box shows its stand-in as the greyed placeholder and gets no
line: the two said the same number twice (desk, 2026-09-24). The line keeps its height
either way, so the table never moves as you type.

**Under the first exit, always: the lowest profitable first exit** (desk
2026-09-24) — the first rung that is a profit on the average for the depth picked, so every
lot sold from there makes money. "Highest profitable" on a short. Full fill at 20.198 reads
"lowest profitable 20.5"; filled to 1 at 20.5 reads 21. Beside a replacement it shortens to
"using lowest profitable 20.5". **A blank first exit now defaults to that rung** (desk,
2026-09-24); it used to be one rung beyond it.

**The yellow box is back on Trade with one job: why 1ST is where it is.** Blank: it is the
lowest rung that is a profit on the average (and what one rung lower would do). Typed: you
set it, and how many rungs above the lowest profitable one it sits. Replaced: why your
number was not a profit, and what is used instead. Nothing else goes in it.
**Removed again** (desk, 2026-09-25): the note inside the 1ST cell ("lowest profitable
21", "using …") already says where 1ST is and when it was replaced.

**Two marker columns.** IN holds `ENTRY` and `STOP`; OUT holds `1ST` and the target. In one shared gutter `ENTRY` and `1ST` sat
side by side on the same rung and read as one thing. Colour now follows the marker rather
than the row — in is blue and red, out is green — because the row colour painted `1ST`
blue whenever it shared a rung with the entry.

**The average out is drawn too**, as a green rule at its true height beside the red one.
The averages carry **no chip** — the rules show where they are and the table says what
they are (desk, 2026-09-24).

**The entry rung can be put back with the entry box empty.** The ladder then builds from
the bid, and the skip handler now does the same; it used to see no rungs at all, so a
click on a default-pulled end never undid it.

## Trade: the right side is a spreadsheet

Desk, 2026-09-24. **The yellow notes box is gone** from the Trade page — it restated what
the tables already show, and the "using X" line under each level now says when a stand-in
or a corrected value is in play. **Everything on the right is a ruled grid**: every cell
bordered, a shaded header row, a shaded label column, figures right-aligned, and the typed
levels sitting flush in their cells. **The big summary number is now a table row** —
position, lots, if stopped, budget, banked — since the averages it showed are in the
levels table.
**That row is gone too** (desk, 2026-09-25): its lots and if-stopped were the picked
fill-depth row, its budget the max loss box, its banked the way-out table's "now" row. The
right side is now levels → fill-depth → way out, nothing twice. In its place the levels table has a
**P&L $ row** under max loss, for the gold-dot row: IN is what that depth loses if stopped
(red), OUT what its way out banks (green) — the LOSS and P&L of the picked row.

**No `FREE` marker on the Trade ladder** (desk, 2026-09-24). The rung the trade stops being
able to lose from is still the first positive row of `if stopped` in the way-out table.

## Trade: levels are snapped to the grid

Audit, 2026-09-24. A bid or a level typed between rungs (21.2, 20.8) used to leave the
ladder with no row for it: lots, flags and the market line silently vanished. Every price
on the page — the bid, entry, stop, first exit, target — is now taken to the nearest 0.5bp
rung, and the box says so ("using 21"). The skip handlers snap the same way, so a click
lands on the rung the page drew.

Nothing on the page is silent any more where it matters: a blank max loss says so in the
box itself ("required"), and Sold typed with nothing in Filled — or more than
is held — says so in the title.

## Trade: each bar beside its own numbers

Desk, 2026-09-25. The way-in bar always sits by the IN column on the left of the spine and
the way-out bar by OUT on the right, long or short. On a short the book would put selling
in on the ask and buying back on the bid, but a bar across the spine from its size read
as belonging to the other half. The colour still says the action: on a short, red going
in (selling), blue coming out (buying back). Long is unchanged.

The headers follow: **IN heads its size and its bar together, OUT likewise** — one
heading centred over each pair. "Bids" and "Asks" are gone; on a short they named the
wrong book.

**The half rules:** a thin blue rule down the outer edge of the IN cells marks the rungs
worked going in (skipped ones included — they are still yours to put back), a green one
down the outer edge of the OUT cells the rungs worked coming out. Each is on its own
cells, so they overlap only where the halves do (entry to 1ST). They were keyed to the
row, so every worked rung drew both and the two ran the whole stop-to-target span.

## Trade: square corners, bold headings

Desk, 2026-09-25. (A Skip ½ button — every other rung pulled in one press — was built and
dropped the same day; skips stay by hand.)

- **Square corners** on the ladder and the bid/ask box. Pills, chips and buttons keep
  theirs.
- **Ladder headings bold** in the main text colour (black on light, white on dark). The
  right-side tables keep their headings as they were.

## Trade: ladder column widths

Desk, 2026-09-25. Every ladder column is a fixed width in pixels, sized to what it holds
and no wider: markers 54 (STOP, ENTRY) and 38 (1ST, TGT), Filled and Sold 44, In and Out
38 each with a 32px bar, price 60, Pos and Left 40 — 460px in all, down from 700. The
Trade panel narrows to match (1080px), and the plans panel stays beside it down to a
~1440px screen.

**No Risk $ or Banked $ on the Trade ladder** (desk, 2026-09-25): they repeated, rung for
rung, the LOSS column of the fill-depth table and the BANKED column of the way-out table.
Pos and Left stay.

**FILLED RISK and IN RISK, far right** (desk, 2026-09-25, later the same day). Each rung's
own dollars to the stop: FILLED RISK on the lots filled there (skipped rungs included),
IN RISK on the lots still to work. Not the Risk $ that went: that was the running loss by
depth, the fill-depth LOSS again; these split the loss across rungs, which nothing else
shows. With nothing filled, IN RISK is equal risk made visible (about the same on every
rung, off only by whole lots); with lots filled, it shows which rung carries the budget.
Plain dollars, no bars. IN RISK greys past the picked depth, as Pos does.

Foot rows under them: **off the ladder** (risk on rungs outside the window drawn),
**sold / banked** (sales leave at the filled average, not off a rung, so FILLED RISK
is taken before them and they come off here), and **total if stopped**, the two
together — the full-fill LOSS. FILLED RISK 70px, IN RISK 60: 590px of columns, the Trade
panel 1210px, the plans panel beside it down to a ~1570px screen. No other column
narrowed to make room.

**OUT P&L, after IN RISK** (desk, 2026-09-25). What each out rung books when it trades:
its lots × distance from the average of the depth picked × $/bp. Not the Banked $ that
went — that was the running total, the way-out table's BANKED again; this is each rung's
own share, and shows which rung carries the money. The foot adds what sales already
banked (on the `sold / banked` row), so its total is the way-out BANKED and the levels
table's P&L OUT. The total row reads `total · if stopped X · if it works Y`. 60px: 650px
of columns, the Trade panel 1270px, the plans panel beside it down to a ~1630px screen.
No Sold P&L column (desk, same day).

**OUT P&L became OUT REGRET** (desk, 2026-09-29), when the way out got its peak (below).
Each out rung's lots × distance to the target × $/bp: the upside those lots give up if
the move runs on. It is the quantity equal regret splits evenly and the out peak bends,
as IN RISK is for the way in, so the column shows the rule working: flat at about the
same figure a rung with the peak off, a hump with it on. The P&L it replaced is still
the fill-depth table's P&L and the way-out table's BANKED. The foot adds what sales
already gave up on the `sold / banked` row, so the total is everything the way out
leaves short of holding the whole position to the target; the label's `if it works` is
still the P&L. 76px for its head.

**`Held` is now `Filled`** (desk, 2026-09-25): the lots already taken. Everywhere on the
page — the column, `Clear filled`, the fill-depth row (`filled @ 6.792`), the depth words
(`filled only`, `filled + 2 rungs`), the messages. The fill-depth table's own first column,
which said `filled` for how deep it fills, is now `depth`, so the word means one thing.
`Sold` stays. Code, stores and saved plans keep the name `held`, so older plans load.

## Trade: the peak

Desk, 2026-09-27. The way in's equal risk can be given a peak: the dollars at risk follow a
bell curve centred on a rung you pick, instead of lying flat. The reasoning and numbers are
in SCALING.md §2; this is how the page carries it.

- **The gold dot**, in a 20px ruled column of its own at the far right (after `Out regret`),
  headed by a gold ● — the same principle as the fill-depth table's dot column, and set
  off from the figures by a rule down its left edge. Click a rung you add at to put it
  there, click it again to take it off; an empty cell shows the dot faintly under the
  mouse. No dot is flat. (It sat left of `Filled` first, blank and unfindable, then with
  a hollow ○ on every pickable rung; both dropped the same day.)
- **Off · Broad · Medium · Narrow**, one segmented control beside RUNGS: on/off and width
  together. Off is the page exactly as it was — equal risk, the dot kept but dimmed and not
  clickable — and picking a width turns it back on where it was.
- **Rungs sized to 0 lots become skips**, derived and re-picked each time; a click puts one
  back. Only with the peak on.
- **A peak off the way in** (entry or stop moved past it) is ignored, not erased: sizing is
  flat and the title says so, and it comes back if the rung does.
- **The footer** names it: `peaked risk in (18, medium, half at ±1.50bp)`.
- **Saved plans** carry the dot and the width. Plans saved before load flat, and do not
  read as changed.
- **All clear** takes the dot off; `+ New plan` also sets the control to Off.
- Width: 670px of ladder columns, the Trade panel 1290px, the plans panel beside it down
  to a ~1650px screen.

## Trade: the peak out

Desk, 2026-09-29. The way in's peak, mirrored onto the way out: the regret each out rung
carries -- the dollars of upside its lots give up if the move runs on to the target --
follows the same bell curve centred on a rung you pick, instead of lying flat. The
arithmetic is `exits.regret_weights`; the reasoning is in SCALING.md §4.

- **Not free, unlike the way in.** Going in, the budget is fixed and the peak only moves
  dollars between rungs. Coming out, the lots are fixed, so total regret -- position ×
  distance from the average out to the target -- moves with the peak, and every dollar
  of it is average exit given up. What it buys is less back-loading.
- **The blue dot**, in its own 20px ruled column right of the gold one. Clickable on the
  rungs still ahead of you on the way out while the peak is on; gold is the way in's, so
  the colour says which half a dot shapes. Both headers now show their colour -- the
  gold one had been painted white by the bold header rule.
- **PEAK OUT: Off · Broad · Medium · Narrow**, its own control beside the way in's, which
  is now labelled PEAK IN. The width is a share of the first exit to the target, as the
  in width is of the entry to the stop. Off is equal regret exactly.
- **Every depth's exit is peaked**, so the fill-depth table's P&L follows it. The width
  is taken on each depth's own first exit.
- **Rungs sized to 0 lots become skips**, derived and re-picked each time, their lots
  re-split by the curve; a click puts one back (live, at whatever it gets), a second
  lets it go. Lots still sum to the position. Only with the peak out on.
- **A peak off the way out** -- behind the furthest sale, or outside first exit to
  target -- is ignored, not erased: equal regret, and the title says so.
- **The footer** names it: `peaked regret out (23, medium, half at ±1.17bp)`.
- **Saved plans** carry the blue dot and its width. Plans saved before load flat and do
  not read as changed. **All clear** takes the dot off; `+ New plan` sets PEAK OUT to Off.
- Width: 706px of ladder columns (the blue dot's 20px, and OUT REGRET 16px wider than
  OUT P&L), the Trade panel 1326px, the plans panel beside it down to a ~1686px screen.

## Trade: the cut past the stop

Desk, 2026-09-30. The stop is the level the trade most likely will not go beyond, where the
way in stops adding. It is no longer the one price every lot is thrown out at. If the
market goes beyond it, the position comes out over the rungs from one past the stop to
**OUT BY**, the level you are fully out by, because only so much P&L can go to one trade.
The reasoning and numbers are in SCALING.md §9, and the arithmetic is in `lib/cuts.py`.

- **OUT BY** is a fifth level. It has a box in the levels table under END, in the IN
  column, and a red flag under STOP in the IN marker column that right-drags like the
  others. It stays at least a rung past the stop, and the stop stays short of it.
- **Blank is the page exactly as before.** The placeholder reads "at stop". A typed OUT BY
  that is not past the stop is ignored, and its cell says so.
- **The cut runs from one rung past the stop through OUT BY.** Nothing is cut at the stop
  itself, the level the trade should hold. The last lots go at OUT BY.
- **Equal loss.** Every cut rung takes the same dollars of loss, the way every rung going
  in puts the same dollars at risk: lots ∝ 1/|avg − x|, getting smaller deeper in the
  cut. It is sized for the depth picked, like the way out, and sums to that position
  exactly.
- **The cut's lots show in OUT, marked red** (desk, 2026-09-30). Cutting a long is
  selling it. So on the cut rungs the lots sit in the Out column, with the way out's bar
  and a red rule down the cell's outer edge where the way out has its green one. `Left`
  counts down to 0 at OUT BY. The cut has no skips, so its cells are not clickable.
- **Max loss covers the trade all the way to OUT BY.** A book cut through every rung loses
  what one stop at the cut's average would. So the way in is sized to that average instead
  of to the stop, through `ladder.plan`'s `risk_to`.
- **The cap is exact, at every depth** (2026-10-04). Whatever rounding does, no row of the
  fill-depth table, cut through OUT BY, loses more than max loss. Checking the full fill
  alone was not enough: with fills typed past the stop, a shallow book's average can sit
  in the cut band, where the cut splits evenly, and that depth lost more than the full
  fill ($1,662.50 at depth 7 on a $1,547 cap). Every depth is checked now, and the way in
  shrinks until all fit. `tests/test_trade_cap.py` holds it.
- **Holding lots past the stop costs lots on the way in.** On the 21.0 → 19.0 long with a
  $5,000 max loss, the way in goes from 144 lots to 93 with OUT BY at 18.
- **Everything on the stop side now measures through OUT BY.**
  - The fill-depth LOSS is each depth's own book cut through OUT BY.
  - The way-out table's stop column is headed "if cut".
  - FILLED RISK and IN RISK measure to the full fill's cut average, so their total is the
    full-fill loss. The ladder's total line reads "if cut".
- **The OUT BY cell's note** is the cut's average for the depth picked ("avg cut 18.279").
  The footer names it as the price the risk in is measured to.
- **A cut you have made goes in `Sold`** on its rung, like any sale. It is banked, as a
  loss, against the filled average. What is still on is re-split over the rungs beyond
  the furthest cut, and the rungs behind it dim as passed.
- **When the filled position is already over the cap,** the title says by how much. That
  is when what is filled loses more than max loss, cut through OUT BY, on its own. The way
  in then adds nothing (it could still add before 2026-10-04, when only the full fill was
  checked). **Without OUT BY the title says it too** (desk, 2026-10-04), measured at the
  stop: "filled loses 7,708 at the -2.5 stop, 2,708 over max loss". It used to appear only
  with a cut, so an over-cap book with a plain stop was silent.
- **The title** adds "18.5 → 18 cut".
- **Saved plans** carry OUT BY. Plans saved before it load with it blank and do not read
  as changed. **All clear** and **+ New plan** blank it.
- **No width change.** The cut uses the Out and Left columns, and OUT BY shares the IN
  marker column with ENTRY and STOP.

## Trade: P&L from settle

Desk, 2026-10-01:

> our statements get marked to market every single day … our books reflect the same as
> if we took the trade at settle

- **A reference, in addition to the trade's own P&L, never instead of it.** It says how
  far the statement moves from last night's mark. Nothing is sized on it: the stop, OUT
  BY, the max loss cap and R:R all stay on the trade.
- **SETTLE**, a box in the levels table under P&L $. Blank shows no settle columns, which
  is the page as before. Off-grid settles are used as typed, not snapped: a settle is
  not a rung.
- **What the statement already shows** is the cell's note, "on books −50": banked from
  Sold, plus the lots still on marked from the filled average to settle. Every
  whole-trade figure from settle is the same figure from entry less this one number.
- **Filled and Sold are the book at settle.** Lots the ladder adds later go on at their
  own rung, which is how they reach the statement. With nothing filled the note reads
  "nothing on yet · same as p&l", and the two sets agree.
- **Where it shows: one row, FROM SETTLE $**, under SETTLE. It is the P&L $ row measured
  from settle: the gold-dot row stopped (in) and what its way out banks (out). Signed, so
  a stop reads negative. Pick a fill-depth row and it follows.
- **Only in the levels table** (desk, 2026-10-01). Settle columns in the fill-depth and
  way-out tables were built and taken out the same day. The levels row is enough.
- **Short 4 at 2.000, settle 2.5:** on books −$50; stopped −$475 from entry is −$425 from
  settle, and works +$438 is +$488.
- **Saved plans** carry the settle. Plans saved before it load blank and do not read as
  changed. **All clear** and **+ New plan** blank it.

## Trade: the levels table, one row height

Desk, 2026-09-25. Start, end, average and max loss are all one height. The notes that
used to sit on a line of their own under a box — which made those rows taller than the
average row — are now **inside the cell**, small and grey on the left, with the number
on the right:

- **Out start (1ST):** always the limit on 1ST — the first rung in profit on the average
  for the depth picked: **"min 21"** on a long, **"max 1"** on a short (desk, 2026-09-25;
  it read "lowest profitable 21", which did not say what it limited). Typed past the
  limit: "below min · using 21" / "above max · using 1". Typed off the grid: "using 21.5 ·
  min 21", or "using 21 · min" when the snap lands on the limit itself.
- **Entry, stop, out end:** "using 21.5" only when your price was off the grid or
  replaced; otherwise nothing.
- **Max loss:** no note — the empty box's placeholder reads **"required"**.
- **Max loss steps by $500** (desk, 2026-09-25): ▼ ▲ on the left of its cell, and the ↑ / ↓
  keys while the box has the cursor. Still a box you can type in. Off-step amounts go to
  the next step in the direction pressed (4,750 → 5,000 or 4,500); a blank box goes up to
  500 and not down; nothing below 500, and ▼ greys out there. The step is written into
  the box as typing is (`assets/trade-loss.js`), so a run of clicks re-sizes once, when
  you stop — done as a callback, quick clicks were folded into one and a number typed a
  moment before overwrote the step. Trade page only.

## Trade: saved plans

Desk, 2026-09-24. A trade action plan you come back to, change and refine as the view
moves. **Its own panel, to the right of the Trade panel** (it drops below it on a screen
narrower than ~1440px): `Reset` and `+ New plan` beside its title, the status line,
`name → Save as new`, a **list of saved plans**, a **short list of the picked plan's
versions**, and the note for the next version. `Save version` is in the Trade panel's head.
Lists rather than dropdowns: every plan and version is in view, and
they take the board's colours in both themes. (Dash's radio list is used underneath, with
plain two-line text labels — component labels made it error and keep the old list when
it grew, so a new version never appeared.)

- **A plan is everything on the page:** instrument, side, bid, entry, stop, first exit,
  target, max loss, Filled and Sold per rung, every skip on both halves, the fill depth
  picked and the rungs count. Loading puts all of it back.
- **Saving never overwrites.** Save adds a new version to the loaded plan, with the note
  if you typed one. The version list reads `v3 · 24 Sep 17:40 · 144 lots, out 22.656 ·
  moved stop` — newest first, the latest loaded by default.
- **Save as new is a different scenario** ("… base" / "… hawkish"), side by side.
- **A snapshot rides with every version** — lots per rung, both averages, if stopped,
  P&L — so a later version can be read against an earlier one even if the sizing rules
  change. Loading always re-sizes from the inputs.
- **The status line** says which version the page came from, with a dot for unsaved
  changes since. The bid loads as it was saved; the save time says how old it is.
- **Reset to vN** (desk, 2026-09-25), under the status line, throws away every change
  since the loaded version — every field, Filled, Sold, skips, depth, rungs — and puts that
  version back. It is live only while there are unsaved changes, and it touches nothing
  on disk. To go back further, click an older version in the list.
- **Archive, not delete:** the file moves to `plans/_archive/`; moving it back restores it.
- **Buttons** (desk, 2026-09-25): one compact style, each beside what it acts on.
  `Reset to vN` and `+ New plan` in the head; `Save as new` beside the name box, above the
  plans; `Archive plan` beside the plan list; `Delete vN` beside the versions.
- **The layout, 2026-10-08** (desk): plans are worked several at a time, versions rarely,
  so the plan list shows about nine and the versions about three, both scrolling.
  `Save version` (filled, the main action — live only when something has changed) ends
  the Trade panel head's first line, right-aligned over `All clear`; its label never
  changes (desk: "changing text in a button is never a good idea"). It saves with the note
  typed under the versions. The head's second line is PEAK IN, PEAK OUT and the clear
  buttons. **Enter** in the note box is `Save version`, and does nothing while it is grey;
  Enter in the name box is `Save as new`.
- **+ New plan** blanks the page — levels, max loss, Filled, Sold, skips, depth, rungs back to
  the default — and ties it to no saved plan; instrument and side stay. Nothing on disk
  changes; name it and `Save as new`.
- **Delete vN** takes the picked version out of its plan, on a second click ("Confirm
  delete vN"; picking another version cancels it). The version is written to
  `plans/_archive/<plan>-vN-<stamp>.json` first. A plan's only version cannot be
  deleted — archive the plan. Numbers are never reused: the plan remembers the highest
  it has handed out (`last_n`), so after v9 is deleted the next save is v10.
- **Files:** `plans/<name>.json`, one per plan with all its versions (`lib/plans.py`).
  Not in git (desk): trade data that changes constantly and keeps its own history.
- **This PC only** (desk, 2026-10-07): with the board on the office network, `Save version`,
  `Save as new`, `Archive plan` and `Delete vN` work only from the PC the board runs on,
  by `127.0.0.1` or its own address. The Risk book is filled from these files, so nobody
  else can change it. From another PC the saves and Archive answer "Plans are saved,
  archived and deleted on the board's own PC only." and Delete stays grey; loading a plan
  and working the page are open to everyone.
- **Trade page only.**

## Trade: shared with the desk (trade-board)

Desk, 2026-10-08. A coworker runs the Trade page on their own PC with their own plans.
`scripts/export_trade.py` builds a separate repo, `..	rade-board`, published on GitHub;
they only pull it, and their Claude sets it up from that repo's `CLAUDE.md`.

- **This repo is the master copy.** A feature is built and committed here, then exported:
  `python scripts/export_trade.py --commit`, then `git -C ..	rade-board push`.
- **What goes:** `trade_page.py`, `lib/` ladder, cuts, exits, plans, the Trade assets,
  `test_trade_cap.py`, `SCALING.md`, plus `share/trade-board/` (launcher on 127.0.0.1:8065,
  `run_trade.cmd`, `backup_plans.cmd`, requirements, README, CLAUDE.md). Read from HEAD,
  never the working copy, so nothing uncommitted goes; `VERSION` names the commit. No other
  page, no data, no plans.
- **Their plans:** `plans/` in their copy, git-ignored there too, so a pull never touches
  them. The launcher listens on 127.0.0.1 only, so on their PC they are the host and saves
  work. CLAUDE.md forbids `git clean -x`, `reset --hard` and re-cloning without a backup.
- **A plan field added later must load blank from older plans**, as OUT BY and settle do:
  their plans were saved by older exports.

## Trade: which lots the exit is sized for

Desk, 2026-09-24. Picking a row of the fill-depth table says which position the way out
is sized for, and the page now shows it in two places:

- **The table:** the picked row gets a blue fill, bold figures (loss still red, P&L still
  green — bold, not recoloured) and a gold dot in a narrow
  column of its own left of `filled` (desk, 2026-09-25: the dot replaced a thin blue bar
  on the row's left edge; every other row's dot cell is empty). Rows deeper than it —
  lots not in the exit — grey out.
- **The ladder:** In rungs deeper than the picked depth grey out (size, bar, Pos, Risk $).
  Filled lots are always counted and stay full strength.
- A dashed "sized to here" line was tried and dropped the same day.

The depth is named in words everywhere: **held only**, **held + 2 rungs**, **full fill**
(was "filled to 0").

## Trade: the rungs counter

Desk, 2026-09-24. Beside Long / Short: **rungs ▼ 10 ▲** (default 10 since 2026-09-25; it
was 14, then 12) — how many rungs are drawn either
side of the market line. Buttons only, not a field; steps of one; held between **8 and
18**, with the arrow greying out at each end. It changes what is on screen and nothing in
the sizing. The ladder is no longer height-capped on Trade, so every rung drawn is visible
without a scroll. It runs in the browser rather than on the server, because server-side two
quick clicks could read the same count and one was lost.
