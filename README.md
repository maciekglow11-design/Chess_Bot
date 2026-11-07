

## Continuous Stockfish coach (optional)

Run repeated games until Ctrl+C, with Stockfish used only as the opponent and post-game reviewer:

```bash
python tools/stockfish_coach.py --stockfish /path/to/stockfish --loop --seconds 1 --analysis-depth 10
```

For a finite batch, use `--games 20` without `--loop`. The tool alternates colors by default and stores:

- `training/strong_games.pgn`: only games meeting the result and largest-move-loss filters (defaults: draw/win and at most 150 cp loss).
- `training/move_review.csv`: each Chess_Bot move, Stockfish's suggested move, and approximate centipawn loss.
- `training/coach_positions.jsonl`: labeled position examples for later experiments.

This is coaching data collection, not automatic engine training. Stockfish analysis does not feed moves to Chess_Bot during play and does not alter its source, evaluation, or search, so the bot does not become a Stockfish copy. To include losses that meet the blunder filter, set `--min-result-score 0`. The measured loss is an approximate depth-limited estimate, not a proof of move quality. Review collected games and tune/test the bot's own heuristics separately before incorporating any changes.

Run the test suite with `python -m unittest discover -s tests -v`.
