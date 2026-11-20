"""Tests for the reference agents (random, greedy, Stockfish).

Stockfish tests are skipped automatically if it isn't installed.
"""

import unittest

import chess

from backend.reference import (GreedyAgent, RandomAgent, StockfishAgent,
                               find_stockfish, make_reference)

HAS_STOCKFISH = find_stockfish() is not None


def play_out(agent, max_plies=400):
    """Let one agent play both sides; return the final board."""
    board = chess.Board()
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < max_plies:
        board.push(agent.play(board))
    return board


class RandomAndGreedyTest(unittest.TestCase):

    def test_random_plays_legal_game(self):
        play_out(RandomAgent(seed=1))           # play() raises on an illegal move

    def test_random_is_reproducible_with_seed(self):
        a, b = play_out(RandomAgent(seed=7), 40), play_out(RandomAgent(seed=7), 40)
        self.assertEqual(a.move_stack, b.move_stack)

    def test_greedy_takes_free_queen(self):
        board = chess.Board("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
        self.assertEqual(GreedyAgent(seed=0).play(board), chess.Move.from_uci("d1d5"))

    def test_greedy_plays_mate_in_one(self):
        board = chess.Board("r5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
        self.assertEqual(GreedyAgent(seed=0).play(board), chess.Move.from_uci("a8a1"))

    def test_greedy_falls_for_defended_piece(self):
        # Greedy can't see the recapture -- that's the point of it.
        board = chess.Board("4k3/8/4p3/3n4/8/8/8/3QK3 w - - 0 1")
        self.assertEqual(GreedyAgent(seed=0).play(board), chess.Move.from_uci("d1d5"))

    def test_make_reference(self):
        self.assertIsInstance(make_reference("random"), RandomAgent)
        self.assertIsInstance(make_reference("greedy"), GreedyAgent)
        with self.assertRaises(ValueError):
            make_reference("magnus")

    def test_missing_stockfish_falls_back_to_greedy(self):
        fallback = make_reference("stockfish", path="/nonexistent/stockfish")
        # Only a fallback if Stockfish is missing everywhere else too.
        if not HAS_STOCKFISH:
            self.assertIsInstance(fallback, GreedyAgent)


@unittest.skipUnless(HAS_STOCKFISH, "Stockfish is not installed")
class StockfishTest(unittest.TestCase):

    def test_finds_mate_in_one(self):
        with StockfishAgent(skill_level=20, think_time=0.1) as sf:
            board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
            self.assertEqual(sf.play(board), chess.Move.from_uci("a1a8"))

    def test_weak_settings_play_legal_moves(self):
        with StockfishAgent(skill_level=0, think_time=0.01, nodes=200) as sf:
            board = chess.Board()
            for _ in range(10):
                board.push(sf.play(board))

    def test_analyse_sees_material(self):
        with StockfishAgent() as sf:
            # White is a queen up.
            score = sf.analyse(chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"), depth=8)
            self.assertGreater(score.white().score(mate_score=100_000), 500)


if __name__ == "__main__":
    unittest.main()
