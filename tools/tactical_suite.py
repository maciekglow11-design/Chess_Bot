#!/usr/bin/env python3
"""Run a small tactical regression suite against the local UCI engine."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = [sys.executable, str(ROOT / "engine.py")]

# FEN, acceptable best moves in UCI, and short description. Positions are
# deliberately simple deterministic checks, not a standardized strength rating.
TACTICS = (
    ("7k/8/5KQ1/8/8/8/8/8 w - - 0 1", {"g6g7", "g6h6", "g6g5"}, "find a mate in one"),
    ("6k1/5ppp/8/8/8/8/5PPP/6KQ w - - 0 1", {"h1d5", "h1a8", "h1b7"}, "win material safely"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", nargs="+", default=DEFAULT_ENGINE,
                        help="UCI engine command; defaults to this repository's engine")
    parser.add_argument("--depth", type=int, default=5)
    args = parser.parse_args()
    if args.depth < 1:
        parser.error("--depth must be positive")

    passed = 0
    with chess.engine.SimpleEngine.popen_uci(args.engine) as engine:
        for fen, expected, description in TACTICS:
            board = chess.Board(fen)
            result = engine.play(board, chess.engine.Limit(depth=args.depth))
            move = result.move
            ok = move is not None and move.uci() in expected
            print(f"{'PASS' if ok else 'CHECK'}: {description}: engine chose {move.uci() if move else 'no move'}")
            passed += int(ok)
    print(f"Matched {passed}/{len(TACTICS)} expected-move sets. A CHECK may mean the test's acceptable moves need review.")
    return 0 if passed == len(TACTICS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
