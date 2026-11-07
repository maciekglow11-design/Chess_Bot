import threading
import unittest

import chess

from engine import SearchLimits, Searcher, evaluate


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
        black_score = evaluate(board)
        self.assertEqual(white_score, -black_score)

    def test_evaluation_is_independent_of_piece_map_iteration_order(self):
        board = chess.Board()
        self.assertEqual(evaluate(board), evaluate(board.copy()))

    def test_mate_is_detected(self):
        board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        self.assertTrue(board.is_checkmate())

    def test_search_finds_mate_in_one(self):
        board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        searcher = Searcher(threading.Event())
        move = searcher.run(board, SearchLimits(max_depth=3))
        board.push(move)
        self.assertTrue(board.is_checkmate(), f"expected mate in one, got {move.uci()}")

    def test_search_returns_legal_move(self):
        board = chess.Board()
        searcher = Searcher(threading.Event())
        move = searcher.run(board, SearchLimits(max_depth=2))
        self.assertIn(move, board.legal_moves)


if __name__ == "__main__":
    unittest.main()
