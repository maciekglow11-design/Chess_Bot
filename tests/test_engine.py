import threading
import unittest

import chess

from engine import SearchLimits, Searcher, evaluate
from opening_book import BOOK, choose_book_move


def perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    nodes = 0
    for move in board.legal_moves:
        board.push(move)
        nodes += perft(board, depth - 1)
        board.pop()
    return nodes


class EngineTests(unittest.TestCase):
    def test_start_position_perft(self):
        board = chess.Board()
        self.assertEqual(perft(board, 1), 20)
        self.assertEqual(perft(board, 2), 400)
        self.assertEqual(perft(board, 3), 8902)

    def test_evaluation_is_side_to_move_relative(self):
        board = chess.Board()
        white_score = evaluate(board)
        board.turn = chess.BLACK
        self.assertEqual(white_score, -evaluate(board))

    def test_evaluation_is_deterministic(self):
        board = chess.Board()
        self.assertEqual(evaluate(board), evaluate(board.copy()))

    def test_search_finds_mate_in_one(self):
        board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=3))
        board.push(move)
        self.assertTrue(board.is_checkmate())

    def test_search_returns_legal_move(self):
        board = chess.Board()
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=2))
        self.assertIn(move, board.legal_moves)

    def test_opening_book_contains_only_legal_start_moves(self):
        board = chess.Board()
        move = choose_book_move(board, randomize=False)
        self.assertIsNotNone(move)
        self.assertIn(move, board.legal_moves)
        self.assertIn(move.uci(), {"e2e4", "d2d4", "c2c4", "g1f3"})

    def test_opening_book_follows_a_known_response(self):
        board = chess.Board()
        board.push_uci("e2e4")
        move = choose_book_move(board, randomize=False)
        self.assertIsNotNone(move)
        self.assertIn(move, board.legal_moves)
        self.assertIn(move.uci(), {"e7e5", "c7c5", "e7e6", "c7c6", "d7d5"})

    def test_book_lines_validate_and_have_positions(self):
        self.assertTrue(BOOK)


if __name__ == "__main__":
    unittest.main()
