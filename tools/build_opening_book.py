#!/usr/bin/env python3
"""Build a Polyglot .bin opening book from one or more PGN files.

Only mainline moves are collected. Frequencies are stored as move weights, not
as quality scores; use PGNs from sources you trust.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

import chess
import chess.pgn
import chess.polyglot


def build_records(paths: list[Path], max_plies: int):
    """Gather (representative board, move-frequency counter) by Polyglot key."""
    records: dict[int, tuple[chess.Board, Counter[chess.Move]]] = {}
    games_read = 0
    for path in paths:
        with path.open("r", encoding="utf-8-sig", errors="replace") as pgn_file:
            while game := chess.pgn.read_game(pgn_file):
                games_read += 1
                if game.errors:
                    print(f"Warning: skipped malformed game in {path}: {game.errors}", file=sys.stderr)
                    continue
                board = game.board()
                for ply, move in enumerate(game.mainline_moves()):
                    if ply >= max_plies:
                        break
                    if move not in board.legal_moves:
                        print(f"Warning: illegal move at ply {ply + 1} in {path}; stopped this game.", file=sys.stderr)
                        break
                    key = chess.polyglot.zobrist_hash(board)
                    if key not in records:
                        records[key] = (board.copy(), Counter())
                    records[key][1][move] += 1
                    board.push(move)
    print(f"Read {games_read} games; found {sum(len(moves) for _, moves in records.values())} position-move pairs.")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn", nargs="+", type=Path, help="Input PGN file(s)")
    parser.add_argument("--output", type=Path, default=Path("opening_book.bin"))
    parser.add_argument("--max-plies", type=int, default=24, help="Maximum half-moves per game")
    parser.add_argument("--min-frequency", type=int, default=1, help="Ignore moves seen fewer times than this")
    args = parser.parse_args()
    if args.max_plies < 1 or args.min_frequency < 1:
        parser.error("--max-plies and --min-frequency must be positive")
    missing = [path for path in args.pgn if not path.is_file()]
    if missing:
        parser.error("PGN file(s) do not exist: " + ", ".join(map(str, missing)))

    records = build_records(args.pgn, args.max_plies)
    written = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with chess.polyglot.open_writer(str(args.output)) as writer:
        for board, moves in records.values():
            for move, frequency in moves.items():
                if frequency < args.min_frequency:
                    continue
                writer.add(board, move, weight=min(65_535, frequency), learn=0)
                written += 1
    print(f"Wrote {written} entries to {args.output.resolve()}")
    print("Only use trusted, high-quality games: move frequency alone is not an engine evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
