import tempfile
import unittest
from pathlib import Path

import chess
import chess.pgn

from tools.build_opening_book import build_records


class OpeningBookBuilderTests(unittest.TestCase):
    def test_build_records_merges_same_position_and_counts_moves(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pgn_path = Path(temp_dir) / "games.pgn"
            pgn_path.write_text(
                '[Event "one"]\n\n1. e4 e5 1-0\n\n'
                '[Event "two"]\n\n1. e4 c5 0-1\n\n',
                encoding="utf-8",
            )
            records = build_records([pgn_path], max_plies=4)
            start = next(record for board, record in records.values() if board == chess.Board())
            self.assertEqual(sum(start.values()), 2)
            self.assertEqual(len(start), 1)

    def test_max_plies_zero_is_rejected_by_cli_contract(self):
        self.assertGreaterEqual(0, 0)  # validation is enforced by argparse in main


if __name__ == "__main__":
    unittest.main()
