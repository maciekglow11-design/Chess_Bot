- Added optional engine style profiles (`balanced`, `aggressive`, `solid`, `endgame`) in `engine.py`.
- Added stockfish coaching loop script `tools/stockfish_coach.py` for repeated games and review logs.
- Added `tools/coach_analysis.py` to summarize recurring mistakes from the coaching CSV.
- Added `tests/test_stockfish_coach.py` for coaching assumptions and defaults.

## Engine styles

The engine exposes a UCI option:

```text
setoption name Style value aggressive
```

Available profiles:
- `balanced`: stable default
- `aggressive`: prioritizes initiative, mobility, queen activity, and attacking chances
- `solid`: stronger king safety and pawn structure discipline
- `endgame`: stronger passed-pawn and rook/endgame evaluation

This keeps the bot recognizable and not a Stockfish clone: the style is internal heuristics, not a move oracle from Stockfish.

## Coaching loop

```bash
python tools/stockfish_coach.py --stockfish /path/to/stockfish --loop --seconds 1 --analysis-depth 10
```

The running mode will:
- play repeated games against Stockfish
- review each Chess_Bot move with Stockfish analysis
- store good games to `training/strong_games.pgn`
- save a statistical CSV and JSONL dataset for later tuning

## Summarize mistakes

```bash
python tools/coach_analysis.py training/move_review.csv --json training/summary.json
```

This highlights recurring mistakes and the positions to improve.
