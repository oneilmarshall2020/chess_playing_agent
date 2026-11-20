"""Optional Stockfish evaluation bar for the GUI (display only).

This is a viewing aid for the human, like a commentator: it shows Stockfish's
opinion of the position on screen and rates each move played. The agents never
see it and never use Stockfish to choose moves.

Stockfish runs in a background thread so the window stays responsive. The GUI
calls ``want()`` every frame with the positions it would like evaluated (most
important first), and ``get()`` to read whatever is ready.
"""

import math
import threading
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

import chess
import chess.engine

from backend.analyse import BLUNDER, EVAL_CAP, INACCURACY, MISTAKE
from backend.reference import find_stockfish

warnings.filterwarnings("ignore", category=DeprecationWarning, module="chess.engine")

ANALYSIS_LIMIT = chess.engine.Limit(depth=12, time=0.5)   # whichever is reached first


@dataclass(frozen=True)
class Evaluation:
    cp: int        # White's advantage in centipawns, clamped to +/-EVAL_CAP (mate = cap)
    text: str      # what to display: "+0.42", "#3", "-#2", "1-0", "1/2-1/2"


def evaluate_board(engine: chess.engine.SimpleEngine, board: chess.Board) -> Evaluation:
    """Stockfish's evaluation of ``board`` from White's point of view."""
    outcome = board.outcome()
    if outcome is not None:                                   # game already over
        if outcome.winner is None:
            return Evaluation(0, "1/2-1/2")
        return Evaluation(EVAL_CAP if outcome.winner else -EVAL_CAP, outcome.result())
    score = engine.analyse(board, ANALYSIS_LIMIT)["score"].white()
    if score.is_mate():
        moves = score.mate()
        return Evaluation(EVAL_CAP if moves > 0 else -EVAL_CAP, f"#{moves}" if moves > 0 else f"-#{-moves}")
    cp = max(-EVAL_CAP, min(EVAL_CAP, score.score()))
    return Evaluation(cp, f"{score.score() / 100:+.2f}")


def white_share(cp: int) -> float:
    """Fraction of the bar that is white (0..1), from White's winning chances.

    Uses the same logistic curve as lichess, so +1 pawn is about 59%, not 100%.
    """
    winning_chances = 2 / (1 + math.exp(-0.00368208 * cp)) - 1     # -1 .. 1
    return 0.5 + 0.5 * winning_chances


def move_symbol(before: Evaluation, after: Evaluation, mover: chess.Color) -> str:
    """Standard annotation for a move from the evaluations before and after it."""
    sign = 1 if mover == chess.WHITE else -1
    loss = sign * (before.cp - after.cp)
    if loss >= BLUNDER:
        return "??"
    if loss >= MISTAKE:
        return "?"
    if loss >= INACCURACY:
        return "?!"
    return ""


class EvalService:
    """Background Stockfish analysis with a cache keyed by FEN."""

    def __init__(self):
        self.path = find_stockfish()
        self.available = self.path is not None
        self._cache: Dict[str, Evaluation] = {}
        self._wanted: List[str] = []
        self._cond = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    def start(self) -> bool:
        """Start the engine thread (once). Returns False if Stockfish is unavailable."""
        if not self.available:
            return False
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return True

    def want(self, fens: List[str]) -> None:
        """Replace the work list: positions to evaluate, most important first."""
        with self._cond:
            seen = set()
            self._wanted = [f for f in fens if f not in self._cache and not (f in seen or seen.add(f))]
            if self._wanted:
                self._cond.notify()

    def get(self, fen: str) -> Optional[Evaluation]:
        return self._cache.get(fen)

    def close(self) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            with chess.engine.SimpleEngine.popen_uci(self.path) as engine:
                while True:
                    with self._cond:
                        while not self._stopping and not self._wanted:
                            self._cond.wait()
                        if self._stopping:
                            return
                        fen = self._wanted.pop(0)
                    if fen not in self._cache:
                        self._cache[fen] = evaluate_board(engine, chess.Board(fen))
        except Exception as error:                          # engine crashed or failed to start
            print(f"[eval bar] Stockfish stopped: {error}")
            self.available = False
