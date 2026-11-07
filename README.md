# Chess_Bot

An experimental UCI chess engine written in Python. `python-chess` supplies legal move generation; this project implements the search and evaluation experiments.

## Run and test

```bash
python -m pip install -r requirements.txt
python engine.py
python -m unittest discover -s tests -v
```

Load the engine in a UCI-compatible GUI. Available UCI options: `Hash`, `Move Overhead`, and `Use Book`.

## Search and evaluation

Current search experiments include iterative deepening, alpha-beta, principal-variation search, aspiration windows, quiescence search, check extensions, late-move reductions, conservative null-move pruning, transposition-table bounds with mate-distance normalization, killer/history/countermove ordering, and static exchange evaluation (SEE) for capture ordering and quiescence pruning. The evaluator covers material, piece activity, pawn structure, passed pawns, bishop pair, rook activity, and a light king-cover term.

These selective search techniques are approximations; they can miss tactics. Regression tests and matches are essential, and a feature is not automatically stronger merely because it is more sophisticated.

## Opening book

A small built-in repertoire is enabled by default. A larger optional Polyglot book can be selected with `CHESS_BOT_BOOK=/path/to/book.bin`. A PGN-to-Polyglot utility is available:

```bash
python tools/build_opening_book.py games.pgn --output opening_book.bin --max-plies 24 --min-frequency 2
```

Frequency alone does not measure move quality; use reliable, legally shareable PGNs.

## Play against Stockfish

Install Stockfish locally, then run:

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 4 --seconds 3 --analysis-depth 12
```

This is a learning project and is not close to grandmaster or Stockfish strength. Improve it through measured changes: run tests, play multiple games at equal settings, and inspect the resulting PGNs.
