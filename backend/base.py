"""Shared player interface.

Every player in the project -- the two Minimax agents, the reference agents
(random, greedy, Stockfish) -- subclasses ``Agent``. The GUI and the match
harness only ever call ``agent.play(board)``, so they never need to know what
kind of player they are talking to.
"""

import threading
from abc import ABC, abstractmethod #keeps the app responsive while the agent runs and makes the class abstract

import chess

# Search-depth limits (in plies) for Minimax agents. Depth 4 is playable in
# pure Python but slow; anything higher is impractical.
MIN_DEPTH, MAX_DEPTH = 1, 4
DEFAULT_DEPTH = 3


def clamp_depth(depth: int) -> int:
    """Force a requested search depth into the [MIN_DEPTH, MAX_DEPTH] range."""
    return max(MIN_DEPTH, min(MAX_DEPTH, int(depth)))


class SearchAborted(Exception):
    """Raised inside a search when ``Agent.abort()`` has been called."""


class Agent(ABC):
    """Base class for anything that can choose a chess move.

    Subclasses implement ``choose_move``. Callers use ``play``, which adds the
    safety checks so every agent behaves the same way.
    """

    def __init__(self, name: str):
        self.name = name
        self._stop = threading.Event()

    # ------------------------------------------------------------------ API
    def play(self, board: chess.Board) -> chess.Move:
        """Return this agent's move for ``board`` without modifying it.

        The agent works on a copy, so a buggy search can never corrupt the
        real game. The returned move is checked for legality.
        """
        if board.is_game_over(claim_draw=True):
            raise ValueError("Cannot choose a move: the game is already over.")

        self._stop.clear()
        move = self.choose_move(board.copy())

        if move not in board.legal_moves:
            raise RuntimeError(f"{self.name} returned an illegal move: {move}")
        return move

    @abstractmethod
    def choose_move(self, board: chess.Board) -> chess.Move:
        """Pick a legal move for the side to move. ``board`` is a private copy."""

    def abort(self) -> None:
        """Ask a running search to stop (e.g. the GUI went back to the menu).

        Long-running agents should call ``check_abort()`` regularly.
        """
        self._stop.set()

    def check_abort(self) -> None:
        """Raise ``SearchAborted`` if ``abort()`` has been requested."""
        if self._stop.is_set():
            raise SearchAborted

    def close(self) -> None:
        """Release external resources (overridden by the Stockfish agent)."""

    def __str__(self) -> str:
        return self.name
