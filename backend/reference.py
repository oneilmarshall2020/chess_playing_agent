"""Reference opponents for testing the two Minimax agents.

These are NOT the assignment's agents; they are fixed yardsticks:

    RandomAgent     - plays any legal move. Anything sensible must beat it.
    GreedyAgent     - looks one move ahead: mates if it can, otherwise grabs
                      the most material. Beats random, but walks into
                      recaptures, so a depth-2+ search should beat it.
    StockfishAgent  - the Stockfish engine at a reduced strength, for a much
                      tougher benchmark and (later) for analysing games.

Use ``make_reference("random" | "greedy" | "stockfish")`` to build one. If
Stockfish is not installed it falls back to GreedyAgent with a warning, so
the project still runs on a machine without it.
"""

import os
import random
import shutil
from typing import Optional

import chess
import chess.engine

from backend.base import Agent
from backend.engine import MATE_SCORE, material_evaluation

# Places Stockfish is commonly installed, checked after $STOCKFISH_PATH and $PATH.
STOCKFISH_LOCATIONS = (
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
)


class RandomAgent(Agent):
    """Chooses uniformly among the legal moves."""

    def __init__(self, name: str = "Random", seed: Optional[int] = None):
        super().__init__(name)
        self.rng = random.Random(seed)

    def choose_move(self, board: chess.Board) -> chess.Move:
        return self.rng.choice(list(board.legal_moves))


class GreedyAgent(Agent):
    """One-ply lookahead on material: checkmate > biggest gain > random.

    It never considers the opponent's reply, which is exactly the weakness
    a Minimax agent should exploit.
    """

    def __init__(self, name: str = "Greedy", seed: Optional[int] = None):
        super().__init__(name)
        self.rng = random.Random(seed)

    def choose_move(self, board: chess.Board) -> chess.Move:
        sign = 1 if board.turn == chess.WHITE else -1   # score from mover's side
        best_moves, best_score = [], None
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                score = MATE_SCORE
            else:
                score = sign * material_evaluation(board)
            board.pop()
            if best_score is None or score > best_score:
                best_moves, best_score = [move], score
            elif score == best_score:
                best_moves.append(move)
        return self.rng.choice(best_moves)


def find_stockfish(path: Optional[str] = None) -> Optional[str]:
    """Locate the Stockfish executable, or return None if it isn't installed.

    Order: explicit ``path`` -> $STOCKFISH_PATH -> $PATH -> common locations.
    """
    candidates = [path, os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish"),
                  *STOCKFISH_LOCATIONS]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class StockfishAgent(Agent):
    """Stockfish behind the ``Agent`` interface, with adjustable strength.

    Strength is controlled three ways (combine as needed):
        skill_level  0 (weakest) .. 20 (full strength); Stockfish then plays
                     deliberately imperfect moves.
        think_time   seconds per move.
        nodes        cap on positions searched per move (very effective at
                     making it weak and is independent of CPU speed).

    The engine process starts on first use; call ``close()`` (or use the
    agent in a ``with`` block) to shut it down.
    """

    def __init__(self, skill_level: int = 0, think_time: float = 0.05,
                 nodes: Optional[int] = None, path: Optional[str] = None,
                 name: Optional[str] = None):
        super().__init__(name or f"Stockfish (skill {skill_level})")
        self.path = find_stockfish(path)
        if self.path is None:
            raise FileNotFoundError(
                "Stockfish not found. Install it, put it on your PATH, or set "
                "STOCKFISH_PATH to the executable.")
        self.skill_level = max(0, min(20, skill_level))
        self.limit = chess.engine.Limit(time=think_time, nodes=nodes)
        self._engine: Optional[chess.engine.SimpleEngine] = None

    def _start(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            self._engine.configure({"Skill Level": self.skill_level})
        return self._engine

    def choose_move(self, board: chess.Board) -> chess.Move:
        return self._start().play(board, self.limit).move

    def analyse(self, board: chess.Board, depth: int = 12) -> chess.engine.PovScore:
        """Stockfish's evaluation of ``board`` (for the match report).

        Note: analysis is always full strength; Skill Level only affects play.
        """
        return self._start().analyse(board, chess.engine.Limit(depth=depth))["score"]

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.quit()
            except chess.engine.EngineTerminatedError:
                pass
            self._engine = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def make_reference(kind: str, seed: Optional[int] = None, **stockfish_options) -> Agent:
    """Build a reference agent by name: "random", "greedy" or "stockfish".

    ``stockfish_options`` are passed to ``StockfishAgent`` (skill_level,
    think_time, nodes, path). Falls back to GreedyAgent if Stockfish is missing.
    """
    kind = kind.lower()
    if kind == "random":
        return RandomAgent(seed=seed)
    if kind == "greedy":
        return GreedyAgent(seed=seed)
    if kind == "stockfish":
        try:
            return StockfishAgent(**stockfish_options)
        except FileNotFoundError as error:
            print(f"[reference] {error} Falling back to GreedyAgent.")
            return GreedyAgent(seed=seed)
    raise ValueError(f"Unknown reference agent: {kind!r} (use random, greedy or stockfish)")
