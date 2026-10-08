@echo off
REM Starts the Trade page at http://127.0.0.1:8065 and opens it in the browser.
REM Uses the .venv in this folder (setup in README.md). Ctrl+C in this window stops it.

cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No .venv here yet. Set it up first -- see README.md, "Setup".
    pause
    exit /b 1
)
start "" http://127.0.0.1:8065
".venv\Scripts\python.exe" scripts\trade_board.py
