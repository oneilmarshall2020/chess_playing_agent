# COMP3220 Chess Agents: Minmax enhanced with Alpha-Beta Pruning

Two chess-playing agents that share one Minimax + Alpha-Beta search engine but
use deliberately different evaluation functions (strategies), plus a pygame GUI
and an agent-vs-agent match harness.

| Agent | Strategy | Built by |
|---|---|---|
| **Aggressive** (`backend/agents/agent_a.py`) | Piece activity, initiative and attacking the enemy king; avoids trades and draws | _Oneil Marshall (ID: )_ |
| **Defensive** (`backend/agents/agent_d.py`) | Loss-averse: king safety, pawn structure, protected pieces; simplifies when ahead | _Sukanayna Hoo (ID: 620173255)_ |

Shared (built together): search engine, GUI, match harness, reference agents, tests.
See `docs/STRATEGIES.md` for how the search works and how the two strategies
differ, and `docs/MATCH_REPORT.md` for the agent-vs-agent results.

---

## 1. Setup

Requires **Python 3.10+** (developed on 3.14).

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt     # python-chess + pygame-ce
```

### Stockfish (optional)

Stockfish is **only** used as a reference opponent and to analyse finished games.
The agents never use it to choose moves. Everything else works without it.

- macOS (Apple Silicon) / Linux: `brew install stockfish` or `sudo apt install stockfish`
- macOS (Intel) / Windows: download the build for your system from
  <https://stockfishchess.org/download/> and put the executable on your `PATH`,
  or point to it with `export STOCKFISH_PATH=/path/to/stockfish`.

If Stockfish isn't found, the `stockfish` opponent falls back to the greedy agent
with a warning.

All commands below are run **from the project root** (the folder containing
`backend/` and `frontend/`), with the virtual environment active (or prefix
them with `venv/bin/`).

## 2. GUI (human vs agent, agent vs agent)

```bash
python -m frontend.app
```

- **Play vs Defensive / Aggressive agent**: choose your colour (White, Black or
  Random) first. Drag or click pieces to move; a promotion picker appears when
  needed. Draw offers and resignation are on the side panel.

- **Agent vs Agent**: the two agents play each other live. Colours alternate
  between games. **Auto** toggles continuous play; **Step** (or Space) plays one
  move at a time.

- **Search depth** (1-4 plies) can be set per agent on the menu; this is the
  difficulty setting. Depth 3 is the default; depth 4 is noticeably slower.

- **<** / **>** (or the arrow keys) step back through the game's history.

- **Board theme**: Classic, Green, Ocean, Purple, Coral or Slate. Cycle it on the
  menu or with **T** during a game. The last move is highlighted on the board
  and in the move list in the theme's highlight colour.

- The window renders at full resolution on Retina / HiDPI screen to not have the GUI images and   
  buttons look soft and low res.

- **Stockfish eval bar** (optional, off by default): toggle it on the menu or
  with **E** during a game. It shows Stockfish's evaluation of the position on
  screen (bar between the board and the panel, score in the status box) and
  marks moves in the move list as `?!` inaccuracy, `?` mistake or `??` blunder.
  It is a **viewing aid only**: it runs separately in `frontend/eval_bar.py`,
  and the agents never see it or use Stockfish to choose their moves.

## 3. Agent-vs-agent match harness

```bash
python -m backend.main aggressive defensive                 # 10 games, depth 3
python -m backend.main aggressive defensive --games 6 --depth-a 2 --depth-b 3
```

- Colours alternate every game. Because the agents are deterministic, each pair
  of games starts from a different standard opening (Italian, Queen's Gambit,
  Sicilian, ...), played once with each agent as White.

- Every game is logged to `logs/<timestamp>_<A>_vs_<B>/`:

  - `games.pgn`: every move, with each agent move annotated with its search
    score, nodes searched and time (opens in any chess GUI, e.g. lichess.org/paste)

  - `results.csv`: one row per game (colours, opening, result, how it ended,
    length, average time and nodes per move, full move list)

  - `summary.txt`: the scoreline, split by colour

Run `python -m backend.main --help` for all options.

### Testing against reference agents

Any of `aggressive`, `defensive`, `random`, `greedy`, `stockfish` can be either player:

```bash
python -m backend.main aggressive greedy --games 4
python -m backend.main defensive stockfish --games 4 --skill 0
```

| Reference | Plays |
|---|---|
| `random` | any legal move |
| `greedy` | mate-in-one if available, otherwise the biggest immediate material gain (no lookahead) |
| `stockfish` | Stockfish at reduced strength (`--skill 0-20`, `--think-time` seconds per move) |

### Stockfish analysis of a match

```bash
python -m backend.analyse logs/<match folder>
```

Stockfish re-evaluates every agent move and reports each agent's average
centipawn loss (how much advantage a move gave away), inaccuracies, mistakes
and blunders, split by opening / middlegame / endgame. It writes `analysis.txt`
and a per-move `analysis.csv` into the match folder. 

## 4. Tests

```bash
python -m unittest discover -s tests -t . -v
```

They cover: mate finding, avoiding hanging pieces, quiescence, Alpha-Beta
returning exactly the Minmax result with far fewer nodes, colour symmetry of
both agents' evaluations, the reference agents, the match harness and the
analysis. Stockfish tests are skipped if it isn't installed.

## 5. Project structure

```
backend/
  base.py          Agent interface (play / abort / close) and depth limits
  engine.py        Shared Minmax + Alpha-Beta search, move ordering, quiescence
  agents/
    __init__.py    Registry: make_player("aggressive" | "defensive" | ...)
    agent_a.py     Aggressive agent: evaluation function
    agent_d.py     Defensive agent: evaluation function
  reference.py     Random, greedy and Stockfish reference agents
  match.py         Match harness and logging
  main.py          Command line for matches
  analyse.py       Stockfish post-game analysis

frontend/
  app.py           GUI: menu, game state, main loop
  board_view.py    GUI: drawing and coordinates
  images/          Piece images

tests/             Unit tests
docs/              Strategy comparison and match report
logs/              Match output (generated)
```

## AI Disclaimer
Generative AI was used to assist in completing this project.
