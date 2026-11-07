# Chess_Bot

A zero-cost, experimental UCI chess engine. It uses `python-chess` for legal move rules and supports a compact built-in opening repertoire plus optional Polyglot books.

## Run and test

```bash
python -m pip install -r requirements.txt
python engine.py
python -m unittest discover -s tests -v
```

Load `engine.py` as a UCI engine in a chess GUI. UCI options: `Hash`, `Move Overhead`, and `Use Book`.

## Improvements

- Iterative deepening, alpha-beta, principal-variation search and aspiration windows.
- Quiescence search, check extensions, late-move reductions, conservative null-move pruning, killer/history move ordering, and a bounded transposition table.
- The TT position key includes the halfmove clock; search checks stop/time/node limits regularly.
- Evaluation includes material, piece activity, pawn structure, passed pawns, bishop pair, rook activity, and a light king-cover term.
- Opening book uses the built-in repertoire and optionally a Polyglot file configured by `CHESS_BOT_BOOK`.

Generate a local Polyglot book from trusted PGNs (move frequency is not a quality score):

```bash
python tools/build_opening_book.py games.pgn --output opening_book.bin --max-plies 24 --min-frequency 2
```

Linux/macOS: `CHESS_BOT_BOOK=opening_book.bin python engine.py`.
PowerShell: `$env:CHESS_BOT_BOOK = (Resolve-Path .\opening_book.bin).Path; python engine.py`.

## Test against Stockfish

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 4 --seconds 3 --analysis-depth 12
```

The engine is a learning project and is nowhere near grandmaster or Stockfish strength yet. Treat each search/evaluation improvement as a hypothesis: run the regression tests and multiple games at equal settings before deciding it made the engine stronger.
