import unittest

import chess

from engine import evaluate


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

    def test_mate_is_detected(self):
        board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        self.assertTrue(board.is_checkmate())


if __name__ == "__main__":
    unittest.main()
