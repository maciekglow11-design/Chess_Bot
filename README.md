# Chess_Bot

A zero-cost, open-source UCI chess engine project. The runnable Python engine uses `python-chess` for legal chess rules and provides a testable foundation for search and evaluation experiments.

## Run the engine

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
python engine.py
```

The program speaks UCI on standard input/output and can be loaded in a UCI-compatible GUI. It supports `uci`, `isready`, `ucinewgame`, `position startpos` / `position fen ...`, `go` with depth, node, clock or move-time limits, `stop`, and `quit`.

## Play against a local Stockfish

Install Stockfish on your computer yourself, then run the match helper. It starts Chess_Bot and Stockfish as local UCI processes, alternates colors by default, prints the moves, reviews Chess_Bot's moves with Stockfish, and writes PGN for later review. It does not download Stockfish or use any paid service.

```bash
python -m pip install -r requirements.txt
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 2 --seconds 1
```

On Windows, pass the executable path, for example `--stockfish C:\\engines\\stockfish.exe`. To use a fixed depth instead of a time limit:

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 2 --depth 6 --analysis-depth 12
```

The default PGN file is `stockfish_games.pgn`. Open it with a chess GUI or share it here. The post-game loss estimates are approximate and depend on the analysis depth; they are intended to locate positions worth investigating, not to prove a move is objectively bad. For a useful comparison, keep the same time/depth for both engines and let the match finish.

## Current engine features

- Legal moves, check, castling, en passant, promotion and draw rules through `python-chess`.
- Iterative-deepening negamax with alpha-beta, principal-variation search and aspiration windows.
- Quiescence search, null-move pruning, a transposition table with mate-distance scores, and PV output.
- Move ordering using TT moves, captures, promotions, killer moves and history heuristic.
- Evaluation for material, piece centralization, pawn structure, passed pawns, bishop pair and king placement.
- UCI `Hash` and `Move Overhead` options; hash entries are retained between searches and cleared for a new game.

The Python `Hash` setting is approximate entry capacity, not byte-accurate allocation. This is an experimental hobby engine, not a claim of being stronger than Stockfish. Python is useful for iteration, but its speed is far below a compiled engine.

## Tests

```bash
python -m unittest discover -s tests -v
```

Next, use the saved games and Stockfish's analysis to identify recurring tactical or positional failures. Fix one class of mistakes at a time and rerun tests and matches.
