import threading
import unittest

import chess

from engine import SearchLimits, Searcher, evaluate, parse_go, score_from_tt, score_to_tt
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

    def test_evaluation_is_symmetric_when_side_to_move_changes(self):
        board = chess.Board()
        score = evaluate(board)
        board.turn = chess.BLACK
        self.assertEqual(score, -evaluate(board))

    def test_evaluation_is_deterministic(self):
        board = chess.Board()
        self.assertEqual(evaluate(board), evaluate(board.copy()))

    def test_evaluation_rewards_rook_on_open_file(self):
        open_file = chess.Board("7k/8/8/8/8/8/8/KR6 w - - 0 1")
        blocked_file = chess.Board("7k/8/8/8/8/8/P7/KR6 w - - 0 1")
        self.assertGreater(evaluate(open_file), evaluate(blocked_file))

    def test_search_finds_mate_in_one(self):
        board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=3))
        board.push(move)
        self.assertTrue(board.is_checkmate())

    def test_search_returns_legal_evasion(self):
        board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=2))
        self.assertIn(move, board.legal_moves)

    def test_search_respects_node_limit(self):
        board = chess.Board()
        move = Searcher(threading.Event()).run(board, SearchLimits(max_depth=8, max_nodes=2_000))
        self.assertIn(move, board.legal_moves)

    def test_book_move_is_legal(self):
        board = chess.Board()
        move = choose_book_move(board, randomize=False)
        self.assertIsNotNone(move)
        self.assertIn(move, board.legal_moves)

    def test_mate_scores_round_trip_through_tt(self):
        for ply in (0, 1, 7, 20):
            for score in (29_990, -29_990, 123, -450):
                self.assertEqual(score_from_tt(score_to_tt(score, ply), ply), score)

    def test_clock_go_limit_uses_position_side_to_move(self):
        board = chess.Board()
        board.push_uci("e2e4")
        limits = parse_go(["go", "wtime", "10000", "btime", "1000", "winc", "0", "binc", "0"], board)
        self.assertIsNotNone(limits.deadline)
        self.assertLess(limits.deadline - __import__("time").monotonic(), 2.0)


if __name__ == "__main__":
    unittest.main()
