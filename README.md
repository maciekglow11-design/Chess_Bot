# Chess_Bot

A zero-cost UCI chess engine project. The Python engine uses `python-chess` for legal move rules and has a compact built-in opening repertoire.

## Run the engine

```bash
python -m pip install -r requirements.txt
python engine.py
```

Load it in a UCI-compatible chess GUI. UCI options include `Hash`, `Move Overhead`, and `Use Book`.

## Opening books

A small built-in book covers common e4, d4, c4 and Nf3 lines. For a larger local book, create a Polyglot `.bin` from trusted PGN games:

```bash
python tools/build_opening_book.py games.pgn --output opening_book.bin --max-plies 24 --min-frequency 2
```

Set `CHESS_BOT_BOOK` to the generated file before starting the engine. Linux/macOS:

```bash
CHESS_BOT_BOOK=opening_book.bin python engine.py
```

PowerShell:

```powershell
$env:CHESS_BOT_BOOK = (Resolve-Path .\opening_book.bin).Path
python engine.py
```

The external book is consulted first; if there is no matching legal entry the engine uses its built-in repertoire and then search. The book builder uses PGN move frequency, not engine quality—prefer high-quality games and check licensing before distributing book files.

## Play against Stockfish

Install Stockfish locally, then run:

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 2 --seconds 3 --analysis-depth 12
```

The helper alternates colors, saves `stockfish_games.pgn` and reports approximate move losses. Share the PGN to diagnose particular mistakes.

## Regression tests

```bash
python -m unittest discover -s tests -v
python tools/tactical_suite.py --depth 5
```

The tactical suite checks selected positions and is not an Elo rating. Search depth depends on time, hardware and Python speed; larger time limits can help analyze tactical errors. This is an experimental engine, not a claim of being stronger than Stockfish.
