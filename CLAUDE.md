# Instructions for Claude: the Trade board

You are setting up, running or updating the **Trade page** on this PC for the person you
are working with. Read all of this before you run anything. The rules under **Their plans**
come before anything else.

## What this is

- **A trade-sizing calculator in the browser.** One trade on one ladder: how many lots
  to put on and take off at each price, for a given max loss. It is a Dash (Python) app
  that runs on this PC only, at `http://127.0.0.1:8065`.
- **Read-only code, from someone else.** It is exported from a larger STIR board (that
  board's owner keeps the master copy) and published at
  `https://github.com/<OWNER>/trade-board`. The person you are working with only
  **pulls**. They cannot push, and you must not commit, push or change any tracked file.
  If they want a change, they ask the board's owner, who adds it and publishes it; then
  you pull it.
- **No market data.** Prices are typed in. Nothing here connects to a feed, a broker or
  the internet.
- `VERSION` says which build of the board this is.

## Their plans: where they are saved and how to keep them safe

- **Where:** `plans\` in this folder. One `.json` file per plan, holding every version
  of it. `plans\_archive\` holds archived plans and deleted versions. Nothing is saved
  anywhere else.
- **The folder appears by itself** the first time they save a plan. Do not create it,
  move it or point the app somewhere else.
- **Git ignores it** (`.gitignore`), so `git pull` never touches it, and their plans
  never go to GitHub.
- **NEVER** do any of these without first backing up `plans\` (see below) and getting
  the person's explicit yes:
  - delete, move or rename this folder, or clone the repo again into it
  - `git clean` with `-x` or `-X` (it wipes ignored files, and that means the plans)
  - `git reset --hard`, `git checkout -- .`, `git stash -u` / `-a`
  - edit, rename or delete anything inside `plans\`
- **Backup:** double-click `backup_plans.cmd`, or run it. It copies `plans\` to
  `%USERPROFILE%\Documents\trade-plans-backup\<date_time>\` and changes nothing in
  `plans\`. Do this before anything that touches the folder.
- **Starting over in a fresh clone:** back up first, clone into a **new** folder, set it
  up, then copy the old `plans\` folder into the new one. Delete the old folder only when
  the person says so, after they have checked their plans load.

## Setup (first time)

Windows. Run these from the folder this file is in.

1. **Check Python is 3.10 or newer** (3.11 is what the owner uses):
   ```
   py -3.11 --version
   ```
   If that fails, try `python --version`. If neither prints 3.10+, ask the person to
   install Python 3.11 from python.org (tick "Add python.exe to PATH"). Do not install
   it yourself without asking.
2. **Check git:** `git --version`.
3. **Clone** (skip this if you are already inside the cloned folder). Ask where they
   want it, e.g. the Desktop:
   ```
   git clone https://github.com/<OWNER>/trade-board.git
   cd trade-board
   ```
4. **Make a private Python environment in this folder**, so nothing else on the PC is
   changed. Use `python` instead of `py -3.11` if that is what worked in step 1:
   ```
   py -3.11 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
5. **Run the tests.** They check the max-loss cap, the page's main rule. Every test must
   pass. If any fail, stop and tell the person. Do not try to fix the code.
   ```
   .venv\Scripts\python -m pytest tests -q
   ```
6. **Start it:** double-click `run_trade.cmd`, or run it. It opens
   `http://127.0.0.1:8065` in the browser. The window it runs in must stay open, and
   Ctrl+C in it stops the board.

## Updating (when the owner says there is something new)

1. **Stop the board** if it is running (Ctrl+C in its window).
2. **Check nothing tracked was changed here:**
   ```
   git status --short
   ```
   `plans\` and `.venv\` never show up, because they are ignored. If any other file
   shows as modified, **stop and ask the person.** Do not discard it. Tracked files are
   not meant to change here, so find out what happened first.
3. **Pull:**
   ```
   git pull --ff-only
   ```
   If it refuses, stop and tell the person. Do not force it, reset or re-clone.
4. **Install anything new** (harmless if nothing changed), then **test**:
   ```
   .venv\Scripts\python -m pip install -r requirements.txt
   .venv\Scripts\python -m pytest tests -q
   ```
5. **Start it again** with `run_trade.cmd`. Their saved plans are all still there. Plans
   saved by an older version load in a newer one: a field added later loads blank.
6. **Tell the person what changed:** `git log --oneline -10` and the new `VERSION`.

## If something goes wrong

- **"Address already in use" / port 8065 busy:** the board is probably already running
  in another window, so use that one. If not, start it on another port with
  `.venv\Scripts\python scripts\trade_board.py --port 8066`.
- **`No module named dash`:** the environment isn't set up, or the wrong Python was used.
  Go back to Setup step 4. Always run through `.venv\Scripts\python`.
- **The page is blank or shows "Updating..." for a long time:** reload the browser tab.
  If it stays blank, read the errors in the board's window and tell the person.
- **Anything in the code looks wrong:** tell the person, and they can tell the owner.
  Do not change code here: the next pull would overwrite it, and it is not theirs to
  change.

## What is in this folder

```
scripts/trade_board.py   the launcher (this PC only, port 8065)
scripts/trade_page.py    everything on the page
lib/ladder.py            sizes the way in against max loss
lib/exits.py             sizes the way out
lib/cuts.py              the cut past the stop (OUT BY)
lib/plans.py             saves and loads plans in plans\
assets/                  the page's look and its two small scripts
tests/                   the max-loss cap tests
docs/SCALING.md          the reasoning behind the sizing
run_trade.cmd            start it
backup_plans.cmd         copy plans\ to Documents
plans/                   THEIR saved plans -- not in git, never touch (see above)
```
