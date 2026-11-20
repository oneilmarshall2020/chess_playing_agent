"""Agent-vs-agent match harness.

Plays a series of games between two agents and logs everything needed for the
match report:

    logs/<timestamp>_<A>_vs_<B>/
        games.pgn     every game, every move (open in any chess GUI / lichess);
                      each agent move is annotated with score, nodes and time
        results.csv   one row per game: colours, opening, result, how it
                      ended, length, average time/nodes per move, SAN moves
        summary.txt   final scoreline, split by colour

Fairness
--------
* Colours alternate every game, cancelling the first-move advantage.
* Both agents are deterministic, so two games from the starting position
  would be identical. Each PAIR of games therefore starts from a different
  standard opening (the first few moves are fixed "book" moves), and within
  a pair each agent plays that opening once as White and once as Black.
"""

import csv
import datetime as dt
import os
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import chess
import chess.pgn

from backend.base import Agent

# Default cap on game length (plies = half-moves). A game reaching it is
# scored as a draw ("move limit"). The 50-move rule usually ends games first.
MAX_PLIES = 300

# Short, well-known openings (SAN). The agents take over after these moves.
OPENINGS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Italian Game", ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")),
    ("Queen's Gambit Declined", ("d4", "d5", "c4", "e6", "Nc3", "Nf6")),
    ("Sicilian Defence", ("e4", "c5", "Nf3", "d6", "d4", "cxd4")),
    ("French Defence", ("e4", "e6", "d4", "d5", "Nc3", "Nf6")),
    ("King's Indian Defence", ("d4", "Nf6", "c4", "g6", "Nc3", "Bg7")),
    ("Ruy Lopez", ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")),
    ("Caro-Kann Defence", ("e4", "c6", "d4", "d5", "Nc3", "dxe4")),
    ("English Opening", ("c4", "e5", "Nc3", "Nf6", "g3", "d5")),
    ("King's Gambit", ("e4", "e5", "f4", "exf4", "Nf3", "d6")),
    ("London System", ("d4", "d5", "Bf4", "Nf6", "e3", "c5")),
]

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


# ------------------------------------------------------------------ records
@dataclass
class GameRecord:
    """Everything about one finished game."""

    number: int
    white: str
    black: str
    opening: str
    result: str                  # "1-0", "0-1" or "1/2-1/2"
    termination: str             # checkmate, stalemate, threefold_repetition, move_limit, ...
    plies: int
    san_moves: List[str]
    times: dict = field(default_factory=dict)   # color -> [seconds per move]
    nodes: dict = field(default_factory=dict)   # color -> [nodes per move] (Minimax agents)
    pgn: Optional[chess.pgn.Game] = None

    @property
    def winner(self) -> Optional[str]:
        return {"1-0": self.white, "0-1": self.black}.get(self.result)

    def average_time(self, color: chess.Color) -> float:
        values = self.times.get(color, [])
        return sum(values) / len(values) if values else 0.0

    def average_nodes(self, color: chess.Color) -> Optional[float]:
        values = self.nodes.get(color, [])
        return sum(values) / len(values) if values else None


@dataclass
class MatchResult:
    """Scoreline of a match between ``name_a`` and ``name_b``."""

    name_a: str
    name_b: str
    games: List[GameRecord] = field(default_factory=list)
    log_dir: Optional[str] = None

    def points(self, name: str) -> float:
        total = 0.0
        for game in self.games:
            if game.result == "1/2-1/2":
                total += 0.5
            elif game.winner == name:
                total += 1
        return total

    def record(self, name: str, color: Optional[chess.Color] = None) -> Tuple[int, int, int]:
        """(wins, draws, losses) for ``name``, optionally only with one colour."""
        wins = draws = losses = 0
        for game in self.games:
            if color is not None and (game.white if color == chess.WHITE else game.black) != name:
                continue
            if game.result == "1/2-1/2":
                draws += 1
            elif game.winner == name:
                wins += 1
            else:
                losses += 1
        return wins, draws, losses

    def summary(self) -> str:
        lines = [f"Match: {self.name_a} vs {self.name_b} ({len(self.games)} games)", ""]
        for name in (self.name_a, self.name_b):
            w, d, l = self.record(name)
            ww, wd, wl = self.record(name, chess.WHITE)
            bw, bd, bl = self.record(name, chess.BLACK)
            lines.append(f"{name:>12}: {self.points(name):4.1f} pts   +{w} ={d} -{l}"
                         f"   (as White +{ww} ={wd} -{wl}, as Black +{bw} ={bd} -{bl})")
        lines += ["", "Endings: " + ", ".join(
            f"{t} x{n}" for t, n in sorted(self._terminations().items()))]
        return "\n".join(lines)

    def _terminations(self) -> dict:
        counts = {}
        for game in self.games:
            counts[game.termination] = counts.get(game.termination, 0) + 1
        return counts


# -------------------------------------------------------------- one game
def play_game(white: Agent, black: Agent, opening: Sequence[str] = (),
              opening_name: str = "Starting position", number: int = 1,
              max_plies: int = MAX_PLIES,
              on_move: Optional[Callable[[chess.Board, chess.Move, Agent], None]] = None
              ) -> GameRecord:
    """Play one game and return its record.

    ``opening`` is a list of SAN book moves played before the agents take
    over. ``on_move`` (optional) is called after every agent move, e.g. to
    print progress. If an agent crashes or returns an illegal move, it loses
    the game (termination "error") instead of stopping the whole match.
    """
    board = chess.Board()
    pgn = chess.pgn.Game()
    pgn.headers.update({
        "Event": "Agent match", "Site": "COMP3220", "Round": str(number),
        "Date": dt.date.today().strftime("%Y.%m.%d"),
        "White": white.name, "Black": black.name, "Opening": opening_name,
    })
    node = pgn
    for san in opening:
        move = board.push_san(san)
        node = node.add_variation(move)
    if opening:
        node.comment = "end of book"

    times = {chess.WHITE: [], chess.BLACK: []}
    nodes = {chess.WHITE: [], chess.BLACK: []}
    result = termination = None

    while board.outcome(claim_draw=True) is None and board.ply() < max_plies:
        color = board.turn
        agent = white if color == chess.WHITE else black
        start = time.perf_counter()
        try:
            move = agent.play(board)
        except Exception as error:                      # the agent forfeits
            result = "0-1" if color == chess.WHITE else "1-0"
            termination = f"error ({agent.name}: {error})"
            break
        seconds = time.perf_counter() - start
        times[color].append(seconds)

        comment = f"{seconds:.2f}s"
        search = getattr(agent, "last_result", None)
        if search is not None:
            nodes[color].append(search.stats.nodes)
            comment = f"score {search.score:+.0f}, {search.stats.nodes} nodes, " + comment

        board.push(move)
        node = node.add_variation(move)
        node.comment = comment
        if on_move:
            on_move(board, move, agent)

    if result is None:
        outcome = board.outcome(claim_draw=True)
        if outcome is not None:
            result, termination = outcome.result(), outcome.termination.name.lower()
        else:
            result, termination = "1/2-1/2", "move_limit"

    pgn.headers["Result"] = result
    pgn.headers["Termination"] = termination
    return GameRecord(number, white.name, black.name, opening_name, result, termination,
                      board.ply(), _san_list(board), times, nodes, pgn)


def _san_list(board: chess.Board) -> List[str]:
    """SAN of every move played on ``board`` (replayed from the start)."""
    replay, sans = chess.Board(), []
    for move in board.move_stack:
        sans.append(replay.san(move))
        replay.push(move)
    return sans


# ------------------------------------------------------------------ match
def run_match(agent_a: Agent, agent_b: Agent, games: int = 10,
              openings: Sequence[Tuple[str, Sequence[str]]] = OPENINGS,
              max_plies: int = MAX_PLIES, log_dir: Optional[str] = DEFAULT_LOG_DIR,
              verbose: bool = True) -> MatchResult:
    """Play ``games`` games between two agents, alternating colours.

    Game 1: A is White, game 2: B is White, both from opening 1; games 3-4
    use opening 2; and so on (openings repeat if games > 2 * len(openings)).
    Logs are written to a new folder inside ``log_dir`` (None = don't log).
    """
    match = MatchResult(agent_a.name, agent_b.name)
    if log_dir:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        match.log_dir = os.path.join(log_dir, f"{stamp}_{_slug(agent_a.name)}_vs_{_slug(agent_b.name)}")
        os.makedirs(match.log_dir, exist_ok=True)

    if verbose:
        print(f"{agent_a.name} vs {agent_b.name}: {games} games"
              + (f", logging to {match.log_dir}" if match.log_dir else ""))

    for i in range(games):
        opening_name, opening = openings[(i // 2) % len(openings)] if openings else ("Starting position", ())
        white, black = (agent_a, agent_b) if i % 2 == 0 else (agent_b, agent_a)
        start = time.perf_counter()
        game = play_game(white, black, opening, opening_name, i + 1, max_plies)
        match.games.append(game)
        if match.log_dir:
            _append_logs(match.log_dir, game)
        if verbose:
            print(f"  game {i + 1:>2}: {white.name} (W) vs {black.name} (B), {opening_name:<24} "
                  f"{game.result:>7}  {game.termination}, {game.plies} plies, "
                  f"{time.perf_counter() - start:.0f}s")

    if match.log_dir:
        with open(os.path.join(match.log_dir, "summary.txt"), "w") as f:
            f.write(match.summary() + "\n")
    if verbose:
        print("\n" + match.summary())
    return match


CSV_FIELDS = ["game", "white", "black", "opening", "result", "winner", "termination", "plies",
              "white_avg_seconds", "black_avg_seconds", "white_avg_nodes", "black_avg_nodes", "moves"]


def _append_logs(folder: str, game: GameRecord) -> None:
    """Add one finished game to games.pgn and results.csv (written as we go,
    so a long match interrupted half-way still has its finished games)."""
    with open(os.path.join(folder, "games.pgn"), "a") as f:
        print(game.pgn, file=f, end="\n\n")

    path = os.path.join(folder, "results.csv")
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        white_nodes, black_nodes = game.average_nodes(chess.WHITE), game.average_nodes(chess.BLACK)
        writer.writerow({
            "game": game.number, "white": game.white, "black": game.black,
            "opening": game.opening, "result": game.result,
            "winner": game.winner or "draw", "termination": game.termination,
            "plies": game.plies,
            "white_avg_seconds": f"{game.average_time(chess.WHITE):.3f}",
            "black_avg_seconds": f"{game.average_time(chess.BLACK):.3f}",
            "white_avg_nodes": "" if white_nodes is None else f"{white_nodes:.0f}",
            "black_avg_nodes": "" if black_nodes is None else f"{black_nodes:.0f}",
            "moves": " ".join(game.san_moves),
        })


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_").lower()
