# Chess_Bot

A zero-cost UCI chess engine project. The Python engine uses `python-chess` for legal move rules and has a compact built-in opening repertoire.

## Run the engine

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
python engine.py
```

Load it in a UCI-compatible chess GUI. The engine supports `uci`, `isready`, `position`, `go` with depth/node/clock limits, `stop`, and `quit`.

## Play against a local Stockfish

Install Stockfish locally, then run:

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 2 --seconds 3
```

Windows example: `python tools/play_stockfish.py --stockfish "C:\\engines\\stockfish.exe" --games 2 --seconds 3`. The helper alternates colors, saves `stockfish_games.pgn`, and can add Stockfish review comments. For longer analysis use `--analysis-depth 14`. Share the PGN to diagnose particular mistakes.

## Improvements in this version

- Compact built-in opening book: common e4, d4, c4 and Nf3 openings and several replies. It plays only positions covered by the repertoire; it is not a full opening database. Disable it in a GUI with `setoption name Use Book value false`.
- Iterative deepening, alpha-beta, principal-variation search, aspiration windows, transposition table and null-move pruning.
- Quiescence search checks captures and promotions; time and node limits are checked regularly.
- Opening book is enabled by default and can be disabled through the UCI `Use Book` option.

## Tests

```bash
python -m unittest discover -s tests -v
```

The built-in book is a small curated baseline, not a substitute for a large verified opening database. Search depth still depends on available time, hardware and Python's speed; increase `--seconds` for longer games. The engine is experimental and is not claimed to match Stockfish strength.
