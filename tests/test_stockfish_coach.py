import unittest

import chess
import chess.engine

from tools.stockfish_coach import bot_result_score, our_color_for_game, score_cp, should_keep_game


class StockfishCoachTests(unittest.TestCase):
    def test_alternates_color_across_continuous_games(self):
        self.assertIs(our_color_for_game("alternate", 1), chess.WHITE)
        self.assertIs(our_color_for_game("alternate", 2), chess.BLACK)
        self.assertIs(our_color_for_game("alternate", 3), chess.WHITE)

    def test_bot_result_score_respects_color(self):
        self.assertEqual(bot_result_score("1-0", chess.WHITE), 1.0)
        self.assertEqual(bot_result_score("1-0", chess.BLACK), 0.0)
        self.assertEqual(bot_result_score("1/2-1/2", chess.BLACK), 0.5)

    def test_keeps_only_good_result_without_large_blunder(self):
        self.assertTrue(should_keep_game("1-0", chess.WHITE, 80, 150))
        self.assertTrue(should_keep_game("1/2-1/2", chess.BLACK, 150, 150))
        self.assertFalse(should_keep_game("0-1", chess.WHITE, 20, 150))
        self.assertFalse(should_keep_game("1-0", chess.WHITE, 151, 150))

    def test_result_threshold_can_include_losses_if_requested(self):
        self.assertTrue(should_keep_game("0-1", chess.WHITE, 20, 150, 0.0))

    def test_score_conversion_uses_requested_perspective(self):
        score = chess.engine.PovScore(chess.engine.Cp(125), chess.WHITE)
        self.assertEqual(score_cp(score, chess.WHITE), 125)
        self.assertEqual(score_cp(score, chess.BLACK), -125)


if __name__ == "__main__":
    unittest.main()
