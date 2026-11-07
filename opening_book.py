"""Small built-in repertoire plus optional Polyglot book support."""

from __future__ import annotations

from collections import Counter, defaultdict
import os
import random
from pathlib import Path

import chess
import chess.polyglot

LINES = (
    "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1 f8e7",
    "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5 c2c3 d7d6",
    "e2e4 e7e5 g1f3 b8c6 d2d4 e5d4 f3d4",
    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6",
    "e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g8f6 b1c3",
    "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 e4e5 f6d7",
    "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4",
    "e2e4 d7d5 e4d5 d8d5 b1c3",
    "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 g1f3",
    "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4 e2e3 e8g8",
    "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6",
    "d2d4 d7d5 c1f4 g8f6 e2e3 e7e6 g1f3",
    "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6",
    "c2c4 g8f6 b1c3 e7e5 g1f3 b8c6",
    "g1f3 d7d5 c2c4 e7e6 d2d4 g8f6",
    "g1f3 g8f6 d2d4 d7d5 c2c4 e7e6",
    "e2e4 e7e5 g1f3 g8f6 f3e5 d7d6 e5f3 f6e4",
    "e2e4 e7e5 g1f3 b8c6 f1b5 g8f6 e1g1 f6e4",
    "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6 b1c3",
    "d2d4 g8f6 c2c4 c7c5 d4d5 e7e6",
)


def build_book() -> dict[int, Counter[chess.Move]]:
    book: dict[int, Counter[chess.Move]] = defaultdict(Counter)
    for line in LINES:
        board = chess.Board()
        for uci in line.split():
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Invalid move {uci!r} in opening line {line!r}")
            book[chess.polyglot.zobrist_hash(board)][move] += 1
            board.push(move)
    return dict(book)


BOOK = build_book()


def _choose_weighted(moves: list[chess.Move], weights: list[int], board: chess.Board,
                     randomize: bool) -> chess.Move:
    if not randomize:
        return max(zip(moves, weights), key=lambda item: (item[1], item[0].uci()))[0]
    rng = random.Random(chess.polyglot.zobrist_hash(board) ^ board.fullmove_number)
    return rng.choices(moves, weights=weights, k=1)[0]


def choose_book_move(board: chess.Board, randomize: bool = True,
                     book_path: str | os.PathLike[str] | None = None) -> chess.Move | None:
    """Use a configured Polyglot book when it has a legal move, else built-in lines.

    Set CHESS_BOT_BOOK to a Polyglot .bin file, or pass book_path explicitly.
    Bad/missing external books are ignored safely so the built-in repertoire works.
    """
    external_path = book_path if book_path is not None else os.environ.get("CHESS_BOT_BOOK")
    if external_path:
        try:
            with chess.polyglot.open_reader(str(Path(external_path))) as reader:
                entries = [entry for entry in reader.find_all(board) if entry.move in board.legal_moves]
            if entries:
                return _choose_weighted(
                    [entry.move for entry in entries],
                    [max(1, entry.weight) for entry in entries], board, randomize,
                )
        except (OSError, ValueError, chess.polyglot.PolyglotError):
            pass

    choices = BOOK.get(chess.polyglot.zobrist_hash(board))
    if not choices:
        return None
    legal = [(move, weight) for move, weight in choices.items() if move in board.legal_moves]
    if not legal:
        return None
    return _choose_weighted([move for move, _ in legal], [weight for _, weight in legal], board, randomize)
