"""Test the Stockfish post-game analysis (skipped without Stockfish)."""

import os
import tempfile
import unittest

from backend.analyse import analyse_folder
from backend.match import run_match
from backend.reference import GreedyAgent, RandomAgent, find_stockfish


@unittest.skipUnless(find_stockfish(), "Stockfish is not installed")
class AnalyseTest(unittest.TestCase):

    def test_greedy_is_more_accurate_than_random(self):
        with tempfile.TemporaryDirectory() as folder:
            match = run_match(GreedyAgent("Greedy", seed=1), RandomAgent("Random", seed=2),
                              games=2, max_plies=60, log_dir=folder, verbose=False)
            stats = analyse_folder(match.log_dir, depth=6, verbose=False)
            self.assertEqual(set(stats), {"Greedy", "Random"})
            self.assertLess(stats["Greedy"].average, stats["Random"].average)
            for name in ("analysis.csv", "analysis.txt"):
                self.assertTrue(os.path.exists(os.path.join(match.log_dir, name)))


if __name__ == "__main__":
    unittest.main()
