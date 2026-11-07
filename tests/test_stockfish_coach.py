import tempfile
import unittest
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from tools.stockfish_coach import (
    bot_result_score,
    keep_best_games,
    our_color_for_game,
    persist_best_games,
    review_our_moves,
    score_cp,
)


class StockfishCoachTests(unittest.TestCase):
    def test_alternates_sides_and_counts_results(self):
        self.assertIs(our_color_for_game("alternate", 1), chess.WHITE)
        self.assertIs(our_color_for_game("alternate", 2), chess.BLACK)
        self.assertEqual(bot_result_score("1-0", chess.WHITE), 1.0)
        self.assertEqual(bot_result_score("1-0", chess.BLACK), 0.0)
        self.assertEqual(bot_result_score("1/2-1/2", chess.BLACK), 0.5)

    def test_best_game_filter_does_not_keep_losing_game_by_default(self):
        game = chess.pgn.Game()
        game.headers["Result"] = "0-1"
        self.assertEqual(keep_best_games([], game, 0, 5, chess.WHITE), [])
        kept = keep_best_games([], game, 0, 5, chess.WHITE, minimum_result_score=0.0)
        self.assertEqual(len(kept), 1)

    def test_persist_does_not_delete_unrelated_pgn(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            unrelated = folder / "my_notes.pgn"
            unrelated.write_text("keep me", encoding="utf-8")
            old = folder / "best_01_100cp.pgn"
            old.write_text("old", encoding="utf-8")
            persist_best_games([], folder)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me")
            self.assertFalse(old.exists())

    def test_score_conversion_handles_zero_and_mates(self):
        score = chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)
        self.assertEqual(score_cp(score, chess.WHITE), 0)
        self.assertEqual(score_cp(score, chess.BLACK), 0)
        mate = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
        self.assertEqual(score_cp(mate, chess.WHITE), 100_000)


if __name__ == "__main__":
    unittest.main()
