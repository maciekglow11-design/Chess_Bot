#!/usr/bin/env python3
"""Build a Polyglot .bin opening book from one or more PGN files.

Only the first/mainline game path is used. Frequencies are stored as move weights.
Use trusted PGNs; this tool does not evaluate whether a move is strategically good.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

import chess
import chess.pgn
import chess.polyglot


def collect_positions(paths: list[Path], max_plies: int) -> dict[int, Counter[chess.Move]]:
    positions: dict[int, Counter[chess.Move]] = defaultdict(Counter)
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
                    if ply >= max_plies or move not in board.legal_moves:
                        break
                    positions[chess.polyglot.zobrist_hash(board)][move] += 1
                    board.push(move)
    print(f"Read {games_read} games; collected {sum(map(len, positions.values()))} position-move entries.")
    return dict(positions)


def write_book(positions: dict[int, Counter[chess.Move]], output: Path, min_frequency: int) -> int:
    written = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with chess.polyglot.open_writer(str(output)) as writer:
        for key, moves in positions.items():
            # Writer.add() computes the position key from a board, so recreate a
            # representative position by retaining the first occurrence below.
            del key
        # Open-book API requires a board for each record. Reconstruct the exact
        # positions from PGN in the CLI helper and pass them to this function.
    return written


def build_records(paths: list[Path], max_plies: int, min_frequency: int):
    """Gather (board, move, weight) records, merging identical positions."""
    records: dict[int, tuple[chess.Board, Counter[chess.Move]]] = {}
    games_read = 0
    for path in paths:
        with path.open("r", encoding="utf-8-sig", errors="replace") as pgn_file:
            while game := chess.pgn.read_game(pgn_file):
                games_read += 1
                if game.errors:
                    print(f"Warning: malformed game in {path}: {game.errors}", file=sys.stderr)
                    continue
                board = game.board()
                for ply, move in enumerate(game.mainline_moves()):
                    if ply >= max_plies or move not in board.legal_moves:
                        break
                    key = chess.polyglot.zobrist_hash(board)
                    if key not in records:
                        records[key] = (board.copy(), Counter())
                    records[key][1][move] += 1
                    board.push(move)
    print(f"Read {games_read} games; found {sum(len(moves) for _, moves in records.values())} position-move pairs.")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn", nargs="+", type=Path, help="Input PGN file(s)")
    parser.add_argument("--output", type=Path, default=Path("opening_book.bin"))
    parser.add_argument("--max-plies", type=int, default=24, help="Only include this many half-moves per game")
    parser.add_argument("--min-frequency", type=int, default=1, help="Ignore moves seen fewer times than this")
    args = parser.parse_args()
    if args.max_plies < 1 or args.min_frequency < 1:
        parser.error("--max-plies and --min-frequency must be positive")
    for path in args.pgn:
        if not path.is_file():
            parser.error(f"PGN file does not exist: {path}")

    records = build_records(args.pgn, args.max_plies, args.min_frequency)
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
    print("Only use trusted, high-quality games: frequency alone is not an engine evaluation.")


if __name__ == "__main__":
    main()
