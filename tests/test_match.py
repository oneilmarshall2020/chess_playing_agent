"""Tests for the match harness (backend/match.py)."""

import os
import tempfile
import unittest

import chess

from backend.base import Agent
from backend.match import play_game, run_match
from backend.reference import GreedyAgent, RandomAgent


class IllegalAgent(Agent):
    def choose_move(self, board):
        return chess.Move.from_uci("a1a8")


class MatchTest(unittest.TestCase):

    def test_play_game_records_everything(self):
        game = play_game(GreedyAgent(seed=1), RandomAgent(seed=2), ("e4", "e5"), "test")
        self.assertIn(game.result, ("1-0", "0-1", "1/2-1/2"))
        self.assertEqual(game.san_moves[:2], ["e4", "e5"])
        self.assertEqual(len(game.san_moves), game.plies)
        self.assertEqual(game.pgn.headers["Result"], game.result)

    def test_move_limit_is_a_draw(self):
        game = play_game(RandomAgent(seed=1), RandomAgent(seed=2), max_plies=10)
        self.assertEqual((game.result, game.termination, game.plies), ("1/2-1/2", "move_limit", 10))

    def test_illegal_move_forfeits(self):
        game = play_game(IllegalAgent("bad"), RandomAgent(seed=1))
        self.assertEqual(game.result, "0-1")
        self.assertTrue(game.termination.startswith("error"))

    def test_colours_alternate_and_logs_written(self):
        a, b = GreedyAgent("A", seed=1), RandomAgent("B", seed=2)
        with tempfile.TemporaryDirectory() as folder:
            match = run_match(a, b, games=4, max_plies=40, log_dir=folder, verbose=False)
            self.assertEqual([g.white for g in match.games], ["A", "B", "A", "B"])
            self.assertEqual(match.games[0].opening, match.games[1].opening)
            self.assertNotEqual(match.games[1].opening, match.games[2].opening)
            self.assertEqual(match.points("A") + match.points("B"), 4)
            for name in ("games.pgn", "results.csv", "summary.txt"):
                self.assertTrue(os.path.exists(os.path.join(match.log_dir, name)))


if __name__ == "__main__":
    unittest.main()
