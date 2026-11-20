# How the agents work, and how their strategies differ

This document explains the shared search (Minimax with Alpha-Beta pruning) and
the two evaluation functions that give each agent its strategy. The results of
the agents playing each other are in [`MATCH_REPORT.md`](MATCH_REPORT.md).

| | Aggressive agent | Defensive agent |
|---|---|---|
| File | `backend/agents/agent_a.py` | `backend/agents/agent_d.py` |
| Designed and built by | Oneil Marshall | Sukanayna Hoo |
| In one sentence | Prioritises piece activity, initiative and attacking the enemy king; keeps pieces on the board and avoids draws. | Loss-averse: prioritises king safety, pawn structure and protected pieces; trades down when ahead. |

## 1. Architecture: one search, two evaluations

Both agents use the **same** search code (`backend/engine.py`). They differ
**only** in the evaluation function they plug into it:

```
                 +-----------------------------+
 board  ------>  |  Minimax + Alpha-Beta       |  ------> best move
                 |  (backend/engine.py)        |
                 +-------------+---------------+
                               | scores leaf positions with
                 +-------------+---------------+
                 | evaluate(board) -> score    |   AggressiveAgent: agent_a.py
                 | (the agent's strategy)      |   DefensiveAgent:  agent_d.py
                 +-----------------------------+
```

This means any difference in how the two agents play comes from their strategic
ideas, not from one having a better search. Both agents search to the same
depth in the match.

**Score convention.** Every score is from **White's point of view, in
centipawns** (100 = one pawn): positive is good for White, negative is good for
Black. White is therefore the *maximising* player and Black the *minimising*
player, exactly as in the textbook form of Minimax.

## 2. Minimax

Minimax chooses a move by looking ahead a fixed number of half-moves (**plies**)
and assuming both sides play their best:

1. From the current position, try every legal move.
2. For each resulting position, recursively try every reply, then every reply
   to that, until the depth limit is reached.
3. Score the positions at the depth limit with the evaluation function.
4. Pass the scores back up the tree: at White's turn take the **maximum** of
   the children, at Black's turn the **minimum**.
5. Play the root move with the best backed-up score.

```text
minimax(board, depth, alpha, beta):
    if the game is over:   return checkmate / draw score
    if depth == 0:         return evaluate(board)          (via quiescence, see 4.2)
    if White to move:
        best = -infinity
        for move in ordered(legal moves):
            best  = max(best, minimax(board after move, depth - 1, alpha, beta))
            alpha = max(alpha, best)
            if alpha >= beta: break                         <- Alpha-Beta cut-off
        return best
    else: (Black to move, mirror image with min / beta)
```

**Game-over positions** are scored without the evaluation function:

| Situation | Score |
|---|---|
| Checkmate | ±(1,000,000 − distance from the root), so a faster mate scores higher and a slower loss is preferred |
| Stalemate, insufficient material, threefold repetition, 50-move rule | 0 (draw), adjusted by the agent's *contempt* (see 4.3) |

**Depth control.** Depth is set per agent, from 1 to 4 plies (default 3). It is
clamped to that range whenever it is set, and the GUI lets the user change it
for each agent. That is the difficulty setting.

## 3. Alpha-Beta pruning

Plain Minimax visits every position in the tree. Alpha-Beta gets **exactly the
same answer** while skipping branches that cannot change it. It carries two
bounds down the tree:

- **alpha**: the best score White is already guaranteed on the path so far;
- **beta**: the best score Black is already guaranteed on the path so far.

If at some node `alpha >= beta`, the player who would have to allow this
position already has a better option elsewhere, so they will never let the
game reach it. The remaining moves at that node are skipped (a **cut-off**).

*Example.* White has already found a move worth +50 (alpha = 50). Exploring a
second White move, the search finds that Black has a reply making it −200.
Black would choose at most −200 there, which is worse for White than the
+50 already available. White will never play this second move, so Black's
other replies don't need to be looked at.

### Evidence that it works

Plain Minimax and Alpha-Beta were run on the same positions with the same
(material-only) evaluation. The test suite (`tests/test_engine.py`) checks that
both give the same move and score, and that Alpha-Beta visits fewer nodes.

| Position | Depth | Minimax nodes | Alpha-Beta, no ordering | Alpha-Beta + move ordering | Nodes saved | Same move & score |
|---|---|---|---|---|---|---|
| Start position | 2 | 420 | 59 | 59 | 86% | yes |
| Start position | 3 | 9,322 | 580 | 580 | 94% | yes |
| Italian Game | 2 | 1,047 | 95 | 94 | 91% | yes |
| Italian Game | 3 | 32,071 | 3,174 | 1,906 | 94% | yes |
| Tactical middlegame | 2 | 2,087 | 691 | 131 | 94% | yes |

Pruning removes 86–94% of the work without changing the decision, and the
saving grows with depth. Move ordering matters most in sharp positions: in the
tactical middlegame it cut the pruned search from 691 to 131 nodes. In quiet
positions with a material-only evaluation, many moves score the same, so the
order makes little difference.

## 4. Search enhancements (shared by both agents)

### 4.1 Move ordering

Alpha-Beta prunes most when the best move is searched first, because a good
early score tightens alpha or beta sooner. Moves are searched in this order:

1. the best move stored for this position in the transposition table (4.3);
2. promotions;
3. captures, by **MVV-LVA** (Most Valuable Victim, Least Valuable Attacker):
   pawn takes queen before queen takes pawn;
4. killer moves (4.4);
5. checks;
6. other quiet moves, by history score (4.4).

Ties keep their order, so the search is deterministic. Before killers and
history were added, only 40% (aggressive) and 53% (defensive) of cut-offs came
from the first move searched (well-tuned engines reach about 90%), which is what
motivated sections 4.3 and 4.4.

### 4.2 Quiescence search

A fixed-depth search can stop in the middle of a capture sequence. For example,
at depth 1 "queen takes a defended knight" looks like +3 because the recapture
is one ply beyond the horizon (the **horizon effect**). At depth 0, instead of
evaluating immediately, the search continues with **captures and promotions
only** until the position is quiet. The side to move may also "stand pat"
(decline all captures), so the static evaluation acts as a bound. This is
tested in `tests/test_engine.py::test_quiescence_fixes_horizon_effect`.

### 4.3 Iterative deepening and transposition table

A depth-3 search runs as depth 1, then 2, then 3. The shallow passes are cheap and
fill a **transposition table**: a cache from each position (reached by any move
order) to its searched depth, score, best move, and whether the score is exact or
only an upper or lower bound (Alpha-Beta cut-offs mean many scores are bounds).
Deeper passes search the stored best move first and reuse scores that were
searched deeply enough. Mate scores are stored relative to the position so they
stay correct when reached at a different distance from the root. Without
iterative deepening the table had 0 hits at depth 3, because the first
transpositions only appear at the leaves.

### 4.4 Killer moves and history heuristic

Quiet (non-capture) moves that cause a cut-off are remembered: the last two per
depth ("killers") and an overall score weighted by depth² ("history"). They are
tried early in sibling positions, where they often cut off again.

**Measured effect** (real agent evaluations, depth 3, six positions, identical
scores in every case):

| Agent | Before | + killers/history | + transposition table + iterative deepening |
|---|---|---|---|
| Aggressive | 139,995 nodes, 28.5 s | −39% nodes, −39% time | **−44% nodes, −41% time** |
| Defensive | 88,218 nodes, 44.3 s | −20% nodes, −29% time | **−28% nodes, −35% time** |

The tests check that the enhanced search returns the same score as plain Minimax
on random positions, and that every transposition-table entry's bound is correct
(this test caught a real bug while the table was being written).

### 4.5 Contempt

An agent can be given a *contempt* value: how much it dislikes a draw. With
contempt 50, a draw counts as −0.5 pawns for the agent choosing the move, so it
avoids repetitions unless it is actually worse. The aggressive agent uses it;
the defensive agent does not (contempt 0).

### 4.6 Responsiveness

The search checks for an abort request every 1,024 nodes and between root
moves, so the GUI can cancel a search (Menu, Restart, Resign) without freezing.
Each agent works on a copy of the board, and `Agent.play()` rejects illegal
moves, so a buggy evaluation can never corrupt the real game.

## 5. The Aggressive agent (Oneil Marshall)

**Strategic identity:** *"How much pressure am I putting on the opponent?"* It
values activity, initiative and attacks on the enemy king. It would rather keep
pieces on the board and the position complicated than simplify, and it treats
a draw as a small loss.

### Evaluation terms (all in centipawns)

| Term | What it rewards | Key weights |
|---|---|---|
| Material | Standard piece values (P 100, N 320, B 330, R 500, Q 900) | Same for both sides |
| Mobility | Each square a piece attacks that isn't occupied by its own pieces | N/B 4, R 2, Q 1 per square |
| Advanced pieces | Minor or major pieces standing in the enemy half | 8 each |
| King attack | Pieces hitting the squares around the enemy king score "attack units" (N/B 2, R 3, Q 5 per square). The bonus is `2 × units²`, capped at 450, and only counts with **2 or more attackers** (a lone piece rarely mates). | Grows quadratically |
| King tropism | Queen, rooks and knights closer to the enemy king | Q 2, R 2, N 3 per square closer |
| Open lines | Rook or queen on an open file at or next to the enemy king | 25 per file |
| Pawn storm | Pawns advanced up the files around the enemy king | 8 per rank advanced |
| Threats | Attacking an enemy piece with a cheaper piece (the opponent must spend a move reacting) | (victim − attacker) / 6 |
| Check | Giving check | 30 |
| **Initiative** | Its **own** attacking terms count 1.3×, the opponent's 1.0×. It values its own attack more than it fears the counter-attack. | 1.3 |
| **Tension** | Bonus proportional to the non-pawn material still on the board, so it avoids trades | material / 40 |
| **King hunt** | In the endgame, when 2+ pawns ahead: push the enemy king to the edge and bring its own king closer, to convert wins | 10 per step from centre, 4 per step closer |
| **Contempt** | A draw counts as −50 | 50 |
| **Piece-square tables** | A bonus or penalty for every piece on every square, written for an attacking style: pawns gain value as they advance (+80 one step from queening), knights want outposts in the enemy half and avoid the rim, rooks want the 7th rank. The king blends a "sheltered" middlegame table and a "central" endgame table by how much material is left (a tapered evaluation). | Whole PST score × 0.5 |

### Design decisions

- **Quadratic king attack with a 2-attacker minimum.** One piece near the king
  is rarely dangerous, and several pieces together are. Squaring the units
  models this, and the cap stops it from ever outweighing a queen.
- **Asymmetric initiative weight.** This is the aggressive mirror of the
  defensive agent's loss aversion. It deliberately accepts some risk to its
  own king in exchange for attacking chances.
- **Queen tropism tuned down from 5 to 2.** At 5, about 30% of the agent's
  first 10 moves were early queen sorties (e.g. `...Qh4 ...Qc4 ...Qg4`),
  which wastes time and lets the opponent develop with tempo. At 2 this fell to
  about 14%, and lower values didn't reduce it further (measured over 16 games
  against the defensive agent). The queen still joins attacks through the
  king-attack and mobility terms.
- **Piece-square tables at half strength.** The PSTs were tested against the
  same agent without them (10 games per setting at depth 2, every move graded
  by Stockfish). At full strength they *hurt*: the positional bonuses tempted
  the agent into moves whose tactical cost lay just beyond its search horizon,
  and it blundered more than without PSTs (34 vs 32). At half strength it
  scored 5.5/10 with fewer blunders (38 vs 43); at quarter strength 6/10
  (33 vs 38). Half strength was kept, so the tables still shape the style.
  Each setting produced different games, so these margins are small and partly
  noise. The consistent finding is that full-strength tables made it worse.
- **Single pass over pieces.** Mobility, advancement, king-zone attacks and
  tropism are computed in one loop using python-chess bitboards. With the PSTs
  the evaluation takes about 0.22 ms per position, which keeps depth 3
  practical in Python.

## 6. The Defensive agent (Sukanayna Hoo)

<!-- Sukanayna: please review and rewrite this section in your own words. The brief
     requires each strategy to be clearly attributable to the partner who built it. -->

**Strategic identity:** *"Is my position safe?"* It values its own material more
than the opponent's (loss aversion), keeps its king sheltered and its pawns
healthy, protects its pieces, and trades pieces off when it is ahead.

### Evaluation terms (all in centipawns)

| Term | What it rewards or penalises | Key weights |
|---|---|---|
| **Loss-averse material** | Its **own** material counts 1.15×, the opponent's 1.0× | 1.15 |
| King safety | King on a castled square (+40). Pawn shield in front of the king (+15 one rank ahead, +8 two ranks ahead, −12 per file with no shield pawn). Enemy attacks on the king and the squares around it (−6 each). | |
| Pawn structure | Doubled pawns −10, isolated pawns −12, pawns protected by another pawn +8 | |
| Piece safety | Protected pieces +3. Hanging (attacked and undefended) pieces −50% of their value. Pieces attacked by a cheaper piece −50% of the difference. An attacking king counts as worth 10,000, so a king can't "win" an exchange against a defended piece. | |
| Development | Knights and bishops off the back rank | 8 each |
| **Simplification** | When 2+ pawns ahead, a bonus that grows as non-pawn material leaves the board, to steer towards a winning endgame | (6400 − non-pawn material) / 20 |
| Draw offers (GUI) | Accepts a human's draw offer unless it is at least 2 pawns ahead after captures settle | |
| **Piece-square tables** | Defensive tables: the king-shelter pawns (f2, g2, h2) are rewarded for staying home and loosening pushes like g4/h4 are penalised; knights guard the centre from their own half (c3/f3) and avoid the rim; bishops favour fianchetto and e2/d2 posts; rooks favour central files and the 2nd rank; the queen is penalised for going deep into enemy territory. The king strongly prefers a castled corner, tapering to a central king in the endgame. Tested against the same agent without them: 7–3, 27 vs 36 blunders. | Whole PST score × 1.0 |

## 7. How the strategies differ, and why

| Question | Aggressive | Defensive |
|---|---|---|
| What does it fear most? | Passivity: positions with no pressure | Losing material |
| Which king does it watch? | The **enemy** king (attack units, tropism, pawn storm, open files) | Its **own** king (castling, pawn shield, attackers nearby) |
| Asymmetric weight | Its own *attack* counts 1.3× | Its own *material* counts 1.15× |
| Trades | Avoids them (tension bonus) | Seeks them when ahead (simplification bonus) |
| Pawns | Pawns are attackers (pawn storm) | Pawns are structure (doubled, isolated, protected) |
| Pieces | Active pieces score (mobility, enemy half) | Safe pieces score (protected, not hanging) |
| Draws | Avoids them (contempt 50) | Neutral (draw = 0) |
| Endgame | Hunts the enemy king when ahead | Simplifies when ahead |

The two functions are not reweightings of the same terms. Only the material
values are shared. Each agent looks at a different king, treats pawns
differently and pulls in opposite directions on trades and draws.

### Expected matchup (tested in the match report)

- The **aggressive** agent should do better in open, tactical positions, and
  against an opponent whose king is short of defenders.
- The **defensive** agent should do better in closed positions and against
  speculative attacks. Its loss aversion makes it hard to trick out of
  material, and it is content to repeat moves, so draws by repetition are
  likely when the aggressive agent's attack stalls.
- Stockfish's analysis should show *where* each agent gives up ground: the
  aggressive agent by over-extending in the middlegame, the defensive agent by
  passivity.

## 8. Verification

`python -m unittest discover -s tests -t .` runs 33 tests, including:

- **Search correctness**: mate in one for both colours, preferring the faster
  mate, taking a free queen, not losing the queen for a defended knight,
  avoiding stalemate when winning, quiescence fixing the horizon effect.
- **Alpha-Beta = Minimax**: same move and score with fewer nodes (section 3); the
  enhanced search (section 4.3–4.4) gives the same score as plain Minimax, and
  transposition-table bounds are verified entry by entry.
- **Both agents**: each evaluation is **colour-symmetric** (a position and its
  mirror image score exactly opposite), which rules out White/Black sign bugs;
  each finds mate in one and takes a free queen.
- **Harness and reference agents**: legal play, colour alternation, logging,
  forfeits on illegal moves, Stockfish analysis.
