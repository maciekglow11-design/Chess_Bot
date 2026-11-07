"""Small built-in, human-curated opening repertoire for Chess_Bot.

This is deliberately a compact repertoire, not a downloaded opening database.
Positions are indexed by Polyglot Zobrist hash and each legal move is weighted by
how many repertoire lines contain it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import random

import chess
import chess.polyglot

# Common beginner-friendly main lines. Moves are UCI and are validated while
# building the book so a typo cannot silently put an illegal move in the book.
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
)


def build_book() -> dict[int, Counter[chess.Move]]:
    book: dict[int, Counter[chess.Move]] = defaultdict(Counter)
    for line in LINES:
        board = chess.Board()
        for uci in line.split():
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Invalid move {uci!r} in opening book line {line!r}")
            book[chess.polyglot.zobrist_hash(board)][move] += 1
            board.push(move)
    return dict(book)


BOOK = build_book()


def choose_book_move(board: chess.Board, randomize: bool = True) -> chess.Move | None:
    """Choose a legal repertoire move for this position, or return None."""
    choices = BOOK.get(chess.polyglot.zobrist_hash(board))
    if not choices:
        return None
    legal = [(move, weight) for move, weight in choices.items() if move in board.legal_moves]
    if not legal:
        return None
    if not randomize:
        return max(legal, key=lambda item: (item[1], item[0].uci()))[0]
    seed = chess.polyglot.zobrist_hash(board) ^ board.fullmove_number
    rng = random.Random(seed)
    return rng.choices([move for move, _ in legal], weights=[weight for _, weight in legal], k=1)[0]
