"""Correctness tests for the shared Minimax / Alpha-Beta search.

Run from the project root:
    venv/bin/python -m unittest discover -s tests -v
"""

import unittest

import chess

from backend.base import MAX_DEPTH, MIN_DEPTH, SearchAborted
from backend.engine import (MATE_SCORE, MinimaxAgent, find_best_move,
                            material_evaluation)


def best(fen, depth, **kwargs):
    return find_best_move(chess.Board(fen), depth, material_evaluation, **kwargs)


class TacticsTest(unittest.TestCase):
    """The search must find and avoid basic tactics."""

    def test_finds_mate_in_one_for_white(self):
        # Back-rank mate: Ra8#
        result = best("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", 2)
        self.assertEqual(result.move, chess.Move.from_uci("a1a8"))
        self.assertGreater(result.score, MATE_SCORE - 10)

    def test_finds_mate_in_one_for_black(self):
        # Same pattern for Black: Ra1#
        result = best("r5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1", 2)
        self.assertEqual(result.move, chess.Move.from_uci("a8a1"))
        self.assertLess(result.score, -(MATE_SCORE - 10))

    def test_prefers_faster_mate(self):
        # At depth 3 the search also sees slower mates; it must still pick Ra8#.
        result = best("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", 3)
        self.assertEqual(result.move, chess.Move.from_uci("a1a8"))

    def test_takes_free_queen(self):
        result = best("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1", 2)
        self.assertEqual(result.move, chess.Move.from_uci("d1d5"))

    def test_does_not_take_defended_knight_with_queen(self):
        # Qxd5 exd5 loses the queen for a knight.
        fen = "4k3/8/4p3/3n4/8/8/8/3QK3 w - - 0 1"
        for quiescence in (False, True):
            result = best(fen, 2, quiescence=quiescence)
            self.assertNotEqual(result.move, chess.Move.from_uci("d1d5"))

    def test_quiescence_fixes_horizon_effect(self):
        # At depth 1 without quiescence, Qxd5 looks like "+1 knight" because
        # the recapture is beyond the horizon. Quiescence sees it.
        fen = "4k3/8/4p3/3n4/8/8/8/3QK3 w - - 0 1"
        self.assertEqual(best(fen, 1, quiescence=False).move, chess.Move.from_uci("d1d5"))
        self.assertNotEqual(best(fen, 1, quiescence=True).move, chess.Move.from_uci("d1d5"))

    def test_avoids_stalemate_when_winning(self):
        board = chess.Board("7k/8/5Q2/8/8/8/8/6K1 w - - 0 1")
        board.push(find_best_move(board, 2, material_evaluation).move)
        self.assertFalse(board.is_stalemate())


class AlphaBetaTest(unittest.TestCase):
    """Alpha-Beta must give exactly the Minimax answer, with fewer nodes."""

    POSITIONS = [
        (chess.STARTING_FEN, 3),
        ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", 3),
        ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 2),
    ]

    def test_same_result_fewer_nodes(self):
        for fen, depth in self.POSITIONS:
            with self.subTest(fen=fen):
                plain = best(fen, depth, alpha_beta=False, quiescence=False)
                pruned = best(fen, depth, alpha_beta=True, quiescence=False)
                self.assertEqual(plain.score, pruned.score)
                self.assertEqual(plain.move, pruned.move)
                self.assertLess(pruned.stats.nodes, plain.stats.nodes)
                self.assertGreater(pruned.stats.cutoffs, 0)
                print(f"\n  depth {depth}: minimax {plain.stats.nodes} nodes, "
                      f"alpha-beta {pruned.stats.nodes} nodes "
                      f"({100 * (1 - pruned.stats.nodes / plain.stats.nodes):.0f}% fewer)")


class AgentTest(unittest.TestCase):

    def test_depth_is_clamped(self):
        agent = MinimaxAgent("t", material_evaluation, depth=99)
        self.assertEqual(agent.depth, MAX_DEPTH)
        agent.depth = 0
        self.assertEqual(agent.depth, MIN_DEPTH)

    def test_play_leaves_board_untouched_and_records_stats(self):
        board = chess.Board()
        agent = MinimaxAgent("t", material_evaluation, depth=2)
        move = agent.play(board)
        self.assertIn(move, board.legal_moves)
        self.assertEqual(board.fen(), chess.STARTING_FEN)
        self.assertGreater(agent.last_result.stats.nodes, 0)

    def test_abort_stops_search(self):
        agent = MinimaxAgent("t", material_evaluation, depth=3)
        agent.abort()
        with self.assertRaises(SearchAborted):
            agent.choose_move(chess.Board())


if __name__ == "__main__":
    unittest.main()
