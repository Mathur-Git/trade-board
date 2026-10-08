"""
The Trade page on its own -- one trade on one ladder: how many lots in and out, for a
given max loss.

    run_trade.cmd              or: python scripts/trade_board.py
    http://127.0.0.1:8065

This PC only: it listens on 127.0.0.1, so nobody else on the network can open it, and
the plans it saves (plans/ in this folder) are this PC's alone.

This file is the frame -- the app, the header and the theme. Everything on the page is
scripts/trade_page.py, and the arithmetic is lib/: ladder.py sizes the way in, exits.py
the way out, cuts.py the cut past the stop (OUT BY), plans.py keeps saved plans on disk.

It is exported from the STIR board, which has more pages. Do not edit the files here: a
pull overwrites them. Changes come from the board's owner.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True          # keep __pycache__ out of lib/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from dash import Dash, Input, Output, State, dcc, html  # noqa: E402

import trade_page       # the Trade page, beside this file   # noqa: E402

HOST = "127.0.0.1"      # this PC only, by design

app = Dash(__name__, assets_folder=str(ROOT / "assets"), title="Trade")

app.layout = html.Div(id="root", className="theme-dark", children=[
    dcc.Store(id="theme-store", data="dark"),
    html.Div(className="shell", children=[
        html.Div(className="global-bar", children=[
            # One page, but the switcher stays: the page reads its plan list from disk
            # whenever it moves, which here is once, at load.
            dcc.RadioItems(id="page", options=["Trade"], value="Trade", inline=True,
                           inputStyle={"display": "none"}, className="seg-ctrl"),
            html.Div(className="title-block", children=[
                html.Span("In and out", className="page-title"),
            ]),
            html.Div(className="bar-right", children=[
                html.Button("Light", id="theme-btn", className="theme-btn"),
            ]),
        ]),
        trade_page.TRADE_PAGE,
    ]),
])


@app.callback(
    Output("theme-store", "data"), Output("root", "className"),
    Output("theme-btn", "children"),
    Input("theme-btn", "n_clicks"), State("theme-store", "data"),
    prevent_initial_call=True,
)
def flip_theme(_, cur):
    nxt = "light" if cur == "dark" else "dark"
    return nxt, f"theme-{nxt}", "Dark" if nxt == "light" else "Light"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="The Trade page")
    ap.add_argument("--port", type=int, default=8065)
    a = ap.parse_args()
    print(f"Trade -> http://{HOST}:{a.port}   (Ctrl+C to stop)")
    try:
        from waitress import serve
    except ImportError:
        serve = None
    if serve is None:
        app.run(debug=False, host=HOST, port=a.port)
    else:
        serve(app.server, host=HOST, port=a.port, threads=4)
