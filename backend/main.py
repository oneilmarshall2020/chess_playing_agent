"""Command-line entry point for running matches.

Run from the project root:

    # The assignment's agent-vs-agent match (10 games, depth 3 each)
    venv/bin/python -m backend.main aggressive defensive

    # Different depths / number of games
    venv/bin/python -m backend.main aggressive defensive --games 6 --depth-a 2 --depth-b 3

    # Test an agent against a reference opponent
    venv/bin/python -m backend.main aggressive stockfish --games 4 --skill 0
    venv/bin/python -m backend.main defensive greedy

Players: aggressive, defensive, random, greedy, stockfish.
Results go to logs/<timestamp>_<A>_vs_<B>/ (games.pgn, results.csv, summary.txt).
"""

import argparse
import sys
import warnings

from backend.agents import PLAYER_NAMES, make_player
from backend.base import DEFAULT_DEPTH, MAX_DEPTH, MIN_DEPTH
from backend.match import DEFAULT_LOG_DIR, MAX_PLIES, OPENINGS, run_match

# python-chess 1.11 triggers a harmless asyncio deprecation warning on Python 3.14.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="chess.engine")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m backend.main",
        description="Play a match between two agents and log the results.")
    parser.add_argument("player_a", choices=PLAYER_NAMES, help="first player")
    parser.add_argument("player_b", choices=PLAYER_NAMES, help="second player")
    parser.add_argument("--games", type=int, default=10,
                        help="number of games, colours alternate (default 10)")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                        help=f"search depth for both Minimax agents, {MIN_DEPTH}-{MAX_DEPTH} "
                             f"(default {DEFAULT_DEPTH})")
    parser.add_argument("--depth-a", type=int, help="override depth for player A")
    parser.add_argument("--depth-b", type=int, help="override depth for player B")
    parser.add_argument("--skill", type=int, default=0, help="Stockfish skill level 0-20 (default 0)")
    parser.add_argument("--think-time", type=float, default=0.05,
                        help="Stockfish seconds per move (default 0.05)")
    parser.add_argument("--max-plies", type=int, default=MAX_PLIES,
                        help=f"game length cap, scored as a draw (default {MAX_PLIES})")
    parser.add_argument("--no-openings", action="store_true",
                        help="start every game from the initial position")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="where to write logs")
    parser.add_argument("--no-log", action="store_true", help="don't write log files")
    return parser.parse_args(argv)


def build_player(name, depth, seed, args):
    return make_player(name, depth=depth, seed=seed,
                       skill_level=args.skill, think_time=args.think_time)


def main(argv=None):
    args = parse_args(argv)
    try:
        a = build_player(args.player_a, args.depth_a or args.depth, 1, args)
        b = build_player(args.player_b, args.depth_b or args.depth, 2, args)
    except (ImportError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    # Two copies of the same agent need different names in the scoreline.
    if a.name == b.name:
        a.name, b.name = f"{a.name} A", f"{b.name} B"

    try:
        run_match(a, b, games=args.games,
                  openings=() if args.no_openings else OPENINGS,
                  max_plies=args.max_plies,
                  log_dir=None if args.no_log else args.log_dir)
    except KeyboardInterrupt:
        print("\nInterrupted - finished games are already in the log folder.")
    finally:
        a.close()
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
