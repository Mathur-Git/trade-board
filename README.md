# Trade board

The Trade page from the STIR board, on its own: one trade on one ladder, how many lots
in and out at each price for a given max loss, with the cut past the stop (OUT BY) and
saved plans.

**Using Claude Code?** Ask it to "set up the Trade board from CLAUDE.md". That file has the
full setup, update and safety steps.

## Setup (Windows, Python 3.10+ and git)

```
git clone https://github.com/<OWNER>/trade-board.git
cd trade-board
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q
```

Then double-click **`run_trade.cmd`**. It opens `http://127.0.0.1:8065`.

## Updating

Stop the board (Ctrl+C in its window), then:

```
git pull --ff-only
.venv\Scripts\python -m pip install -r requirements.txt
```

and start it again.

## Your plans

- **Saved in `plans\` in this folder**, one file per plan with all its versions.
  Archived plans and deleted versions go to `plans\_archive\`.
- **Not in git:** a pull never touches them, and they never leave this PC.
- **Deleting or re-cloning this folder deletes them.** Run **`backup_plans.cmd`** first.
  It copies them to `Documents\trade-plans-backup\`.
- **This PC only:** the board listens on `127.0.0.1`, so nobody else can open it or
  change your plans.

## Changes

This copy is read-only. Don't edit the files here, because the next pull overwrites
them. Ask the board's owner for changes.
