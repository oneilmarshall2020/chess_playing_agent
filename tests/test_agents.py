"""Sanity tests run against BOTH partners' agents.

These don't judge strategy -- only that each evaluation is sign-correct and
the agent plays obvious tactics.
"""

import importlib
import unittest

import chess

AGENTS = [("backend.agents.agent_a", "AggressiveAgent"),
          ("backend.agents.agent_d", "DefensiveAgent")]

POSITIONS = [
    chess.STARTING_FEN,
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/8/8/4k3/8/8/3QK3/8 w - - 0 1",
]


def make(module_name, class_name, depth=2):
    return getattr(importlib.import_module(module_name), class_name)(depth=depth)


class AgentSanityTest(unittest.TestCase):

    def test_agents_import(self):
        for module_name, class_name in AGENTS:
            with self.subTest(agent=class_name):
                make(module_name, class_name)

    def test_evaluation_is_colour_symmetric(self):
        """A position and its mirror image (colours swapped) must score
        exactly opposite. Catches White/Black sign mistakes."""
        for module_name, class_name in AGENTS:
            with self.subTest(agent=class_name):
                agent = make(module_name, class_name)
                for fen in POSITIONS:
                    board = chess.Board(fen)
                    agent.color = chess.WHITE
                    white_view = agent.evaluate_board_state(board)
                    agent.color = chess.BLACK
                    black_view = agent.evaluate_board_state(board.mirror())
                    self.assertAlmostEqual(white_view, -black_view, delta=1, msg=fen)

    def test_finds_mate_in_one(self):
        for module_name, class_name in AGENTS:
            with self.subTest(agent=class_name):
                board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
                self.assertEqual(make(module_name, class_name).play(board),
                                 chess.Move.from_uci("a1a8"))

    def test_takes_free_queen(self):
        for module_name, class_name in AGENTS:
            with self.subTest(agent=class_name):
                board = chess.Board("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
                self.assertEqual(make(module_name, class_name).play(board),
                                 chess.Move.from_uci("d1d5"))


if __name__ == "__main__":
    unittest.main()
