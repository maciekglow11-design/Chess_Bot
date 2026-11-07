# Chess_Bot

A zero-cost, experimental UCI chess engine. `python-chess` supplies legal move generation; this project implements evaluation, search, opening-book selection, and tools for testing.

## Run and test

```bash
python -m pip install -r requirements.txt
python engine.py
python -m unittest discover -s tests -v
```

Load `engine.py` in any UCI-compatible GUI. UCI options: `Hash`, `Move Overhead`, `Use Book`, and `SyzygyPath`.

## New evaluation and search work

- Phase-aware middlegame/endgame piece-square terms for every piece.
- Evaluation includes material, piece activity/mobility, doubled/isolated/connected/passed pawns, bishop pair, open and semi-open rook files, seventh-rank rooks, knight outposts, king shelter, and nearby king pressure.
- Correct side-to-move score symmetry: no asymmetric tempo constant is added.
- Search uses iterative deepening, alpha-beta, PVS, aspiration windows, quiescence, check extensions, late-move reductions, conservative null-move pruning, killer/history/countermove ordering, and a generation-aware transposition table with selective replacement.
- Repetition-sensitive nodes are not stored/reused in the transposition table; the halfmove clock is part of the key.
- Optional Syzygy probing for positions with at most seven pieces. Configure the folder containing Syzygy table files through `setoption name SyzygyPath value /path/to/syzygy` in a UCI GUI. Table files are not included.

Search pruning is selective and can still miss tactics. The optional Syzygy feature only applies when the necessary local table files are present. These additions do not make a Python project grandmaster- or Stockfish-strength; measure changes with tests and paired games.

## Opening book

The built-in repertoire is enabled by default. Generate an optional Polyglot book from trusted PGNs (move frequency is not a quality score):

```bash
python tools/build_opening_book.py games.pgn --output opening_book.bin --max-plies 24 --min-frequency 2
```

Set `CHESS_BOT_BOOK` to the generated file before starting the engine.

## Match against local Stockfish

```bash
python tools/play_stockfish.py --stockfish /path/to/stockfish --games 4 --seconds 3 --analysis-depth 12
```

The helper saves PGN and provides approximate move-loss reports. The engine is a learning project; evaluate strength through repeatable tournaments, not feature count.
