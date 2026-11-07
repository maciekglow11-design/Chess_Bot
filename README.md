# Chess_Bot

A zero-cost, open-source UCI chess engine project.

## Run

```bash
python -m pip install -r requirements.txt
python engine.py
```

## Features

- Legal moves, checks, castling, en passant, promotion and draw detection via `python-chess`.
- Compact opening repertoire with a built-in book and optional Polyglot book support.
- Iterative-deepening alpha-beta search with move ordering, killer moves and history heuristics.
- Quiescence search, transposition table and tactical checks.
- UCI `Hash`, `Move Overhead` and `Use Book` options.

## Test

```bash
python -m unittest discover -s tests -v
```

## Local Stockfish match

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 2 --seconds 2 --analysis-depth 12
```

This is still a hobby engine; the goal is stable improvement step by step, not a Stockfish clone.
