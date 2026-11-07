import threading
import unittest

import chess

from engine import SearchLimits, Searcher, evaluate, static_exchange_eval
from opening_book import choose_book_move


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

    def test_search_finds_mate_in_one(self):
        board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=3))
        board.push(move)
        self.assertTrue(board.is_checkmate())

    def test_search_returns_legal_move_when_checked(self):
        board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=2))
        self.assertIn(move, board.legal_moves)

    def test_search_respects_node_limit(self):
        board = chess.Board()
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=8, max_nodes=2_000))
        self.assertIn(move, board.legal_moves)

    def test_opening_move_is_legal(self):
        board = chess.Board()
        move = choose_book_move(board, randomize=False)
        self.assertIsNotNone(move)
        self.assertIn(move, board.legal_moves)

    def test_static_exchange_detects_poisoned_queen_capture(self):
        board = chess.Board("k3r3/8/8/4p3/4Q3/8/8/K7 w - - 0 1")
        move = chess.Move.from_uci("e4e5")
        self.assertIn(move, board.legal_moves)
        self.assertLess(static_exchange_eval(board, move), 0)

    def test_static_exchange_values_unprotected_pawn_capture(self):
        board = chess.Board("k7/8/8/4p3/4Q3/8/8/K7 w - - 0 1")
        move = chess.Move.from_uci("e4e5")
        self.assertIn(move, board.legal_moves)
        self.assertGreater(static_exchange_eval(board, move), 0)

    def test_evaluation_is_deterministic(self):
        board = chess.Board()
        self.assertEqual(evaluate(board), evaluate(board.copy()))


if __name__ == "__main__":
    unittest.main()
