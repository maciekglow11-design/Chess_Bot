import unittest

import chess

from tools.play_stockfish import our_color_for_game, score_cp


class MatchToolTests(unittest.TestCase):
    def test_alternates_sides_between_games(self):
        self.assertIs(our_color_for_game("alternate", 1), chess.WHITE)
        self.assertIs(our_color_for_game("alternate", 2), chess.BLACK)
        self.assertIs(our_color_for_game("alternate", 3), chess.WHITE)

    def test_fixed_color_selection(self):
        self.assertIs(our_color_for_game("white", 2), chess.WHITE)
        self.assertIs(our_color_for_game("black", 1), chess.BLACK)

    def test_score_conversion_uses_requested_perspective(self):
        score = chess.engine.PovScore(chess.engine.Cp(125), chess.WHITE)
        self.assertEqual(score_cp(score, chess.WHITE), 125)
        self.assertEqual(score_cp(score, chess.BLACK), -125)


if __name__ == "__main__":
    unittest.main()
