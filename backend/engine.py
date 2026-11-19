"""
Score convention
----------------
Every score is from WHITE's point of view, in centipawns (100 = one pawn):
    positive -> good for White, negative -> good for Black.
So White is the MAX player and Black is the MIN player. An evaluation function therefore has the form

    evaluate(board: chess.Board) -> float   # White's advantage

How the search works
--------------------
1. Minmax: from the current position, try every legal move, recursively
   score the resulting positions down to a fixed depth (plies), and assume
   both sides pick the move that is best for them (White maximises, Black
   minimises). Positions at depth 0 are scored by the evaluation function.
2. Alpha-Beta pruning: carry two bounds down the tree:
       alpha = best score White is already guaranteed elsewhere
       beta  = best score Black is already guaranteed elsewhere
   As soon as alpha >= beta, the opponent would never allow this line, so
   the remaining moves at that node are skipped ("cut off"). The result is
   identical to plain Minmax, but far fewer positions are visited.
3. Move ordering: Alpha-Beta prunes most when good moves are searched first,
   so captures (most valuable victim first), promotions and checks go first.
4. Quiescence search (optional, on by default): instead of evaluating a
   position in the middle of a capture sequence, keep searching captures
   only until the position is "quiet". This avoids the horizon effect, e.g.
   taking a defended piece because the recapture is just past the depth limit.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import chess

from backend.base import DEFAULT_DEPTH, Agent, clamp_depth

Evaluator = Callable[[chess.Board], float]

# Larger than any evaluation can be. A mate found ``ply`` moves from the root
# scores MATE_SCORE - ply, so a faster mate is always preferred.
MATE_SCORE = 1_000_000
DRAW_SCORE = 0

# Limit on how many captures deep quiescence search may go.
MAX_QUIESCENCE_DEPTH = 8

# Check for an abort request every this many nodes (must be a power of two).
ABORT_CHECK_INTERVAL = 1024

# Standard piece values in centipawns. Shared because move ordering needs
# them; agents are free to use their own values in their evaluation.
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def material_evaluation(board: chess.Board) -> float:
    """Baseline evaluation: material balance only (White minus Black).

    Used by the tests and as a neutral reference; NOT either partner's agent.
    """
    score = 0
    for piece_type, value in PIECE_VALUES.items():
        score += value * len(board.pieces(piece_type, chess.WHITE))
        score -= value * len(board.pieces(piece_type, chess.BLACK))
    return score


# --------------------------------------------------------------- move ordering
def move_order_key(board: chess.Board, move: chess.Move) -> int:
    """Heuristic priority of a move: higher is searched first.

    - Promotions first (a new queen is almost always strong).
    - Captures ordered by MVV-LVA: Most Valuable Victim, Least Valuable
      Attacker (pawn takes queen before queen takes pawn).
    - Checks next; quiet moves last.
    """
    key = 0
    if move.promotion:
        key += 20_000 + PIECE_VALUES[move.promotion]
    if board.is_capture(move):
        # En passant: the captured pawn is not on the destination square.
        victim = board.piece_type_at(move.to_square) or chess.PAWN
        attacker = board.piece_type_at(move.from_square)
        key += 10_000 + 10 * PIECE_VALUES[victim] - PIECE_VALUES[attacker]
    if board.gives_check(move):
        key += 5_000
    return key


def order_moves(board: chess.Board, moves) -> List[chess.Move]:
    """Return ``moves`` sorted best-guess-first (stable, so ties keep order)."""
    return sorted(moves, key=lambda m: move_order_key(board, m), reverse=True)

@dataclass
class SearchStats:
    """Counters describing one search, for the GUI and the documentation."""

    depth: int = 0
    nodes: int = 0               # positions visited (including quiescence)
    evaluations: int = 0         # calls to the evaluation function
    cutoffs: int = 0             # times Alpha-Beta pruned the remaining moves
    seconds: float = 0.0


@dataclass
class SearchResult:
    move: Optional[chess.Move]
    score: float                 # from White's point of view
    stats: SearchStats = field(default_factory=SearchStats)


class Search:
    """One Minmax search over a position.

    Parameters
    ----------
    evaluate:     the evaluation function (White's point of view).
    alpha_beta:   prune with Alpha-Beta (False = plain Minmax, for testing).
    quiescence:   extend leaf positions with a captures-only search.
    abort_check:  called every ABORT_CHECK_INTERVAL nodes; it may raise
                  ``SearchAborted`` to stop the search.
    """

    def __init__(self, evaluate: Evaluator, alpha_beta: bool = True,
                 quiescence: bool = True,
                 abort_check: Optional[Callable[[], None]] = None):
        self.evaluate = evaluate
        self.alpha_beta = alpha_beta
        self.quiescence = quiescence
        self.abort_check = abort_check
        self.stats = SearchStats()

    # -------------------------------------------------------------- root
    def run(self, board: chess.Board, depth: int) -> SearchResult:
        """Search ``board`` to ``depth`` plies and return the best move.

        Ties are broken in favour of the move searched first, which makes the
        search deterministic (same position + depth -> same move).
        """
        if depth < 1:
            raise ValueError("depth must be at least 1")
        self.stats = SearchStats(depth=depth)
        start = time.perf_counter()

        maximizing = board.turn == chess.WHITE
        alpha, beta = -math.inf, math.inf
        best_move = None
        best_score = -math.inf if maximizing else math.inf

        for move in order_moves(board, board.legal_moves):
            if self.abort_check:                       # also check between root moves
                self.abort_check()
            board.push(move)
            score = self.minmax(board, depth - 1, alpha, beta, ply=1)
            board.pop()

            if (maximizing and score > best_score) or (not maximizing and score < best_score):
                best_move, best_score = move, score
            if maximizing:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)

        self.stats.seconds = time.perf_counter() - start
        return SearchResult(best_move, best_score, self.stats)

    # --------------------------------------------------------- recursion
    def minmax(self, board: chess.Board, depth: int, alpha: float,
                beta: float, ply: int) -> float:
        """Minmax value of ``board`` searched ``depth`` more plies.

        ``ply`` is the distance from the root, used to prefer faster mates.
        """
        self._visit()

        # Draws by rule. (Repetition is checked against the real game history
        # plus the line being searched, so agents avoid/seek repetitions.)
        if (board.is_insufficient_material() or board.halfmove_clock >= 100
                or board.is_repetition(3)):
            return DRAW_SCORE

        moves = list(board.legal_moves)
        if not moves:
            if board.is_check():                       # checkmate
                return -(MATE_SCORE - ply) if board.turn == chess.WHITE else MATE_SCORE - ply
            return DRAW_SCORE                          # stalemate

        if depth <= 0:
            if self.quiescence:
                return self.quiesce(board, alpha, beta, 0)
            return self._evaluate(board)

        maximizing = board.turn == chess.WHITE
        best = -math.inf if maximizing else math.inf

        for move in order_moves(board, moves):
            board.push(move)
            score = self.minmax(board, depth - 1, alpha, beta, ply + 1)
            board.pop()

            if maximizing:
                best = max(best, score)
                alpha = max(alpha, best)
            else:
                best = min(best, score)
                beta = min(beta, best)

            if self.alpha_beta and alpha >= beta:
                self.stats.cutoffs += 1
                break                                  # opponent avoids this line
        return best

    def quiesce(self, board: chess.Board, alpha: float, beta: float,
                qdepth: int) -> float:
        """Captures-only search so leaves are evaluated in quiet positions.

        "Stand pat": the side to move may decline every capture, so the static
        evaluation is a lower bound (White) / upper bound (Black) on the score.
        """
        self._visit()
        stand_pat = self._evaluate(board)
        if qdepth >= MAX_QUIESCENCE_DEPTH:
            return stand_pat

        maximizing = board.turn == chess.WHITE
        best = stand_pat
        if maximizing:
            if best >= beta:
                return best
            alpha = max(alpha, best)
        else:
            if best <= alpha:
                return best
            beta = min(beta, best)

        captures = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        for move in order_moves(board, captures):
            board.push(move)
            score = self.quiesce(board, alpha, beta, qdepth + 1)
            board.pop()

            if maximizing:
                best = max(best, score)
                alpha = max(alpha, best)
            else:
                best = min(best, score)
                beta = min(beta, best)
            if alpha >= beta:
                self.stats.cutoffs += 1
                break
        return best

    # ------------------------------------------------------------ helpers
    def _visit(self) -> None:
        self.stats.nodes += 1
        if self.abort_check and self.stats.nodes & (ABORT_CHECK_INTERVAL - 1) == 0:
            self.abort_check()

    def _evaluate(self, board: chess.Board) -> float:
        self.stats.evaluations += 1
        return self.evaluate(board)


def find_best_move(board: chess.Board, depth: int, evaluate: Evaluator,
                   alpha_beta: bool = True, quiescence: bool = True) -> SearchResult:
    """Convenience wrapper: search a copy of ``board`` and return the result."""
    return Search(evaluate, alpha_beta, quiescence).run(board.copy(), depth)


class MinmaxAgent(Agent):
    """An ``Agent`` that chooses moves with the shared Minmax search.

    Each partner's agent is a ``MinmaxAgent`` with its own ``evaluate``.
    ``depth`` can be changed between moves (the GUI's difficulty buttons)
    and is always kept inside [MIN_DEPTH, MAX_DEPTH].
    """

    def __init__(self, name: str, evaluate: Evaluator, depth: int = DEFAULT_DEPTH,
                 alpha_beta: bool = True, quiescence: bool = True):
        super().__init__(name)
        self.evaluate = evaluate
        self.depth = depth
        self.alpha_beta = alpha_beta
        self.quiescence = quiescence
        self.last_result: Optional[SearchResult] = None

    @property
    def depth(self) -> int:
        return self._depth

    @depth.setter
    def depth(self, value: int) -> None:
        self._depth = clamp_depth(value)

    def choose_move(self, board: chess.Board) -> chess.Move:
        search = Search(self.evaluate, self.alpha_beta, self.quiescence,
                        abort_check=self.check_abort)
        self.last_result = search.run(board, self.depth)
        return self.last_result.move
