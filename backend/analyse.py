"""Stockfish post-game analysis for the match report.

Stockfish acts as a neutral judge: for every move an agent played, it
evaluates the position before and after the move. The difference is the
"centipawn loss" (CPL): how much of its advantage the agent threw away with
that move (0 = Stockfish agrees it was the best move).

Per agent this gives:
    average CPL      lower = more accurate play
    inaccuracies     moves losing >= 50 cp  (half a pawn)
    mistakes         moves losing >= 100 cp (a pawn)
    blunders         moves losing >= 300 cp (a piece)
and the same split into opening / middlegame / endgame, which is useful for
explaining WHERE each strategy is strong or weak.

Usage (from the project root):
    venv/bin/python -m backend.analyse logs/<match folder>
    venv/bin/python -m backend.analyse logs/<match folder> --depth 14

Writes <match folder>/analysis.csv (one row per agent move) and
<match folder>/analysis.txt (the summary table), and prints the summary.
Book moves (the fixed opening) are not counted.
"""

import argparse
import csv
import os
import sys
import warnings
from dataclasses import dataclass, field
from typing import Dict, List

import chess
import chess.engine
import chess.pgn

from backend.reference import find_stockfish

warnings.filterwarnings("ignore", category=DeprecationWarning, module="chess.engine")

DEFAULT_DEPTH = 12
EVAL_CAP = 1000            # clamp evals to +/-10 pawns so moves in already-won/lost
                           # positions don't dominate the averages (mate = cap)
INACCURACY, MISTAKE, BLUNDER = 50, 100, 300
OPENING_PLIES = 20         # phase boundaries: plies 1-20 = opening ...
ENDGAME_MATERIAL = 1300    # ... and total non-pawn material <= this = endgame

NON_PAWN_VALUES = {chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900}


@dataclass
class AgentStats:
    moves: int = 0
    total_loss: float = 0.0
    inaccuracies: int = 0
    mistakes: int = 0
    blunders: int = 0
    by_phase: Dict[str, List[float]] = field(
        default_factory=lambda: {"opening": [], "middlegame": [], "endgame": []})

    def add(self, loss: float, phase: str) -> None:
        self.moves += 1
        self.total_loss += loss
        self.by_phase[phase].append(loss)
        if loss >= BLUNDER:
            self.blunders += 1
        elif loss >= MISTAKE:
            self.mistakes += 1
        elif loss >= INACCURACY:
            self.inaccuracies += 1

    @property
    def average(self) -> float:
        return self.total_loss / self.moves if self.moves else 0.0

    def phase_average(self, phase: str) -> str:
        values = self.by_phase[phase]
        return f"{sum(values) / len(values):.0f}" if values else "-"


def game_phase(board: chess.Board) -> str:
    """Opening / middlegame / endgame of the position BEFORE a move."""
    if board.ply() < OPENING_PLIES:
        return "opening"
    material = sum(value * len(board.pieces(pt, color))
                   for pt, value in NON_PAWN_VALUES.items() for color in chess.COLORS)
    return "endgame" if material <= ENDGAME_MATERIAL else "middlegame"


def white_eval(engine: chess.engine.SimpleEngine, board: chess.Board, depth: int) -> int:
    """Stockfish's score of ``board`` from White's view, clamped to +/-EVAL_CAP."""
    if board.is_game_over(claim_draw=True):
        outcome = board.outcome(claim_draw=True)
        if outcome.winner is None:
            return 0
        return EVAL_CAP if outcome.winner == chess.WHITE else -EVAL_CAP
    score = engine.analyse(board, chess.engine.Limit(depth=depth))["score"].white()
    return max(-EVAL_CAP, min(EVAL_CAP, score.score(mate_score=EVAL_CAP)))


def book_length(game: chess.pgn.Game) -> int:
    """Number of opening book plies (the harness marks the last one)."""
    for ply, node in enumerate(game.mainline(), start=1):
        if node.comment == "end of book":
            return ply
    return 0


def analyse_folder(folder: str, depth: int = DEFAULT_DEPTH, verbose: bool = True) -> Dict[str, AgentStats]:
    pgn_path = os.path.join(folder, "games.pgn")
    if not os.path.exists(pgn_path):
        raise FileNotFoundError(f"No games.pgn in {folder}")
    path = find_stockfish()
    if path is None:
        raise FileNotFoundError("Stockfish is required for analysis but was not found.")

    stats: Dict[str, AgentStats] = {}
    rows = []
    with chess.engine.SimpleEngine.popen_uci(path) as engine, open(pgn_path) as pgn_file:
        number = 0
        while (game := chess.pgn.read_game(pgn_file)) is not None:
            number += 1
            names = {chess.WHITE: game.headers["White"], chess.BLACK: game.headers["Black"]}
            skip = book_length(game)
            board = game.board()
            before = white_eval(engine, board, depth)
            for ply, move in enumerate(game.mainline_moves(), start=1):
                mover, phase, san = board.turn, game_phase(board), board.san(move)
                board.push(move)
                after = white_eval(engine, board, depth)
                if ply > skip:
                    sign = 1 if mover == chess.WHITE else -1
                    loss = max(0, sign * (before - after))
                    stats.setdefault(names[mover], AgentStats()).add(loss, phase)
                    rows.append({"game": number, "ply": ply, "agent": names[mover], "move": san,
                                 "phase": phase, "eval_before": before, "eval_after": after,
                                 "centipawn_loss": loss})
                before = after
            if verbose:
                print(f"  analysed game {number} ({board.ply()} plies)")

    with open(os.path.join(folder, "analysis.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["game"])
        writer.writeheader()
        writer.writerows(rows)
    report = summary(stats, depth)
    with open(os.path.join(folder, "analysis.txt"), "w") as f:
        f.write(report + "\n")
    if verbose:
        print("\n" + report)
    return stats


def summary(stats: Dict[str, AgentStats], depth: int) -> str:
    lines = [f"Stockfish analysis (depth {depth}); centipawn loss per move, lower is better",
             "",
             f"{'Agent':<14}{'moves':>6}{'avg CPL':>9}{'inacc.':>8}{'mistakes':>10}{'blunders':>10}"
             f"{'opening':>9}{'middle':>8}{'endgame':>9}"]
    for name, s in stats.items():
        lines.append(f"{name:<14}{s.moves:>6}{s.average:>9.0f}{s.inaccuracies:>8}{s.mistakes:>10}"
                     f"{s.blunders:>10}{s.phase_average('opening'):>9}"
                     f"{s.phase_average('middlegame'):>8}{s.phase_average('endgame'):>9}")
    lines += ["", f"inaccuracy >= {INACCURACY} cp, mistake >= {MISTAKE} cp, blunder >= {BLUNDER} cp; "
                  f"phase columns = average CPL in that phase"]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.analyse",
                                     description="Analyse a match's games with Stockfish.")
    parser.add_argument("folder", help="a match folder inside logs/")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                        help=f"Stockfish analysis depth (default {DEFAULT_DEPTH})")
    args = parser.parse_args(argv)
    try:
        analyse_folder(args.folder, args.depth)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
