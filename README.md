# Chess_Bot

A zero-cost, open-source UCI chess engine project. The first implementation is a runnable Python engine focused on correct chess rules (provided by `python-chess`), search, and a testable foundation. Python keeps experimentation accessible without a compiler or paid compute.

## Run

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
python engine.py
```

The program speaks UCI on standard input/output. Load it in a UCI-compatible GUI such as Arena, BanksiaGUI, or Cute Chess. You can also try it from a terminal:

```text
uci
isready
position startpos
go depth 5
```

It supports `uci`, `isready`, `ucinewgame`, `position startpos` / `position fen ...`, `go` with depth, node, clock or move-time limits, `stop`, and `quit`.

## Current features

- Legal moves, check, castling, en passant, promotion and draw rules through `python-chess`.
- Iterative-deepening negamax with alpha-beta, principal-variation search and aspiration windows.
- Quiescence search, null-move pruning, a transposition table with mate-distance scores, and PV output.
- Move ordering using TT moves, captures, promotions, killer moves and history heuristic.
- Evaluation for material, piece centralization, pawn structure, passed pawns, bishop pair and king placement.
- UCI `Hash` and `Move Overhead` options; hash entries are retained between searches and cleared for a new game.
- Perft regression tests and a tactical mate-in-one search test.

Set options in a UCI GUI or send commands such as `setoption name Hash value 32` and `setoption name Move Overhead value 50`. Hash is an approximate entry-capacity setting in this Python version, not a byte-accurate allocation; 1 MB maps to about 1,500 entries.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Next steps

1. Expand perft and tactical test positions.
2. Add a repeatable self-play/tournament harness to measure strength changes.
3. Profile before optimizing; Python is an accessible prototype, not a route to Stockfish-class speed.
4. Improve evaluation and search one measurable change at a time.
5. Consider a C++ core or NNUE only after the baseline and tests are reliable.

This is an experimental hobby engine, not a claim of being stronger than Stockfish. Training and testing can be done locally without paid services; free hosted GPU runtimes are optional and have changing limits.
