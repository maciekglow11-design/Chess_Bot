# Chess_Bot

A zero-cost, open-source UCI chess engine project. The first implementation is a complete, runnable Python engine focused on correct chess rules (provided by `python-chess`), a usable search, and a testable foundation. Python is intentionally used for the first version so development and experiments do not require a compiler or paid compute.

## Run

Python 3.10+ is recommended.

```bash
python -m pip install -r requirements.txt
python engine.py
```

The program speaks UCI on standard input/output. Load it in a UCI-compatible GUI such as Arena, BanksiaGUI, or Cute Chess. These are optional; you can also try it from a terminal:

```text
uci
isready
position startpos
go depth 5
```

The engine supports `uci`, `isready`, `ucinewgame`, `position startpos` / `position fen ...`, `go` with depth, node, clock or move-time limits, `stop`, and `quit`.

## Current features

- Legal moves, check, castling, en passant, promotion and draw rules through `python-chess`.
- Iterative-deepening negamax with alpha-beta pruning.
- Quiescence search, transposition table, mate-distance scores, and principal-variation output.
- Move ordering using transposition-table moves, captures, promotions, killer moves and history heuristic.
- Basic evaluation for material, piece centralization, pawn structure, passed pawns, bishop pair and king placement.
- Perft regression tests for the opening position.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Roadmap

1. Keep move-generation correctness covered by perft and tactical test positions.
2. Add a repeatable self-play/tournament harness and record engine versions and settings.
3. Profile before optimizing; Python is an accessible prototype, not the route to Stockfish-class speed.
4. Improve evaluation and search one measurable change at a time.
5. Consider a C++ search/move-generation core or a small NNUE only after the baseline and tests are reliable.

This is an experimental hobby engine, not a claim of being stronger than Stockfish. Training and testing can be done locally without paid services; free hosted GPU runtimes are optional and have changing limits.
