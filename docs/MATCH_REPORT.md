# Match report: Aggressive vs Defensive

**Final score: Aggressive 5.5, Defensive 4.5** (10 games, both agents at search depth 3).

How the agents and the search work is explained in [`STRATEGIES.md`](STRATEGIES.md).
The raw data is in `logs/20261120_022321_aggressive_vs_defensive/`: `games.pgn`
(every move, annotated with score, nodes and time), `results.csv`, `summary.txt`,
and Stockfish's move-by-move grading in `analysis.csv` / `analysis.txt`.

## 1. Setup

| Setting | Value |
|---|---|
| Games | 10 |
| Search depth | 3 plies for both agents (same search engine, so only the evaluation differs) |
| Colours | Alternate every game |
| Openings | Five standard openings, each played twice so that each agent has it once as White and once as Black. Both agents are deterministic, so without this, games would repeat. |
| Game end | Checkmate, stalemate, threefold repetition, 50-move rule, insufficient material, or a 300-ply cap (scored as a draw; never reached) |
| Move grading | Stockfish 19, depth 12, every non-book move (centipawn loss; inaccuracy >= 50, mistake >= 100, blunder >= 300) |

## 2. Results

| Game | White | Black | Opening | Result | Ending | Length (plies) |
|---|---|---|---|---|---|---|
| 1 | Aggressive | Defensive | Italian Game | 0-1 | Checkmate | 66 |
| 2 | Defensive | Aggressive | Italian Game | 0-1 | Checkmate | 58 |
| 3 | Aggressive | Defensive | Queen's Gambit Declined | ½-½ | Threefold repetition | 49 |
| 4 | Defensive | Aggressive | Queen's Gambit Declined | 1-0 | Checkmate | 109 |
| 5 | Aggressive | Defensive | Sicilian Defence | 0-1 | Checkmate | 94 |
| 6 | Defensive | Aggressive | Sicilian Defence | 0-1 | Checkmate | 90 |
| 7 | Aggressive | Defensive | French Defence | 1-0 | Checkmate | 23 |
| 8 | Defensive | Aggressive | French Defence | 1-0 | Checkmate | 133 |
| 9 | Aggressive | Defensive | King's Indian Defence | 1-0 | Checkmate | 95 |
| 10 | Defensive | Aggressive | King's Indian Defence | 0-1 | Checkmate | 26 |

| Agent | Points | Won / Drawn / Lost | As White | As Black |
|---|---|---|---|---|
| **Aggressive** | **5.5** | 5 / 1 / 4 | 2 / 1 / 2 | 3 / 0 / 2 |
| Defensive | 4.5 | 4 / 1 / 5 | 2 / 0 / 3 | 2 / 1 / 2 |

Nine of the ten games ended in checkmate; one was drawn by repetition.

### Stockfish's grading of every move

| Agent | Moves | Avg centipawn loss | Inaccuracies | Mistakes | Blunders | Opening | Middlegame |
|---|---|---|---|---|---|---|---|
| Aggressive | 342 | **69** | 52 | 47 | 22 | 92 | **63** |
| Defensive | 341 | 73 | **40** | 48 | **20** | 94 | 68 |

Lower is better. No positions were classed as endgames: every game was decided
while queens or several pieces were still on the board.

### Search effort

| Agent | Avg time per move | Avg positions searched per move |
|---|---|---|
| Aggressive | 1.09 s | 6,157 |
| Defensive | 1.79 s | 4,839 |

## 3. Analysis: how the results follow from the strategies

**The match was close, and the two agents won in different ways.** The 5.5–4.5
score and the almost identical accuracy (69 vs 73 centipawns lost per move) say
the agents are of similar strength. With 10 games the margin is within
noise. *How* each one won is more revealing than the score.

**The aggressive agent wins fast; the defensive agent wins slowly.** The
aggressive agent's five wins averaged **58 plies**, including mates in 23 and 26
plies. The defensive agent's four wins averaged **100 plies**. This is what the
evaluations predict:
- the aggressive agent rewards attack units around the enemy king, open files,
  pawn storms and checks, so it builds direct mating attacks;
- the defensive agent rewards safe pieces and a sound structure, so it wins by
  outlasting attacks and slowly converting.

**Game 7: the attack the aggressive agent was built for.** After the French
Defence book moves, it played `e5`, `Bd3` and the pawn storm `h4`. As soon as
Black castled, it played the classic bishop sacrifice:

> 7. h4 O-O 8. **Bxh7+!** Kxh7 9. Qd3+ Kg8 10. Ng5 Re8 11. Qh7+ Kf8 12. **Qh8#**

Every piece involved is rewarded by its evaluation:
- the h-pawn by the pawn-storm term;
- the queen and knight by king tropism;
- the bishop sacrifice by the quadratic king-attack bonus, which only pays out
  once two or more pieces join.

Stockfish rated the defensive agent's `O-O` a blunder. Its king-safety term and
PSTs reward a castled king with a pawn shield, but at depth 3 it couldn't see the
sacrifice that tears the shield open. This shows the weakness of a *static* idea
of safety.

**Game 10: the defensive agent's material instinct backfires.** In the King's
Indian, the defensive agent grabbed a pawn with `10. Qxb7`, rated its only blunder of
the game. Its queen left the defence, and the aggressive agent's pieces poured in
with checks (`Qa5+`, `Nxd4+`, `Qe1+`, `Nc2+`). The White king was forced up the
board and mated on f4 after 26 plies. Loss aversion makes the defensive agent
value material highly. Grabbing material is fine against a passive opponent,
but here it removed the queen from the king's defence.

**The defensive agent's wins come from surviving and outlasting.** In games 4
and 8 (109 and 133 plies) it absorbed the attack. In game 8, Stockfish recorded
four aggressive-agent blunders after move 38, as it kept attacking (`Qh3` twice,
`Kh8`, `Rf8`) in a position that no longer justified it. This is the cost of the
aggressive agent's 1.3× weight on its own initiative: it overrates attacks
that have run out of steam.

**The only draw is a repetition the aggressive agent couldn't avoid.** In game 3
its queen shuttled between g5 and h6 while Black's bishop answered on e7 and f8.
Its contempt setting makes a draw worth −0.5 pawns to it, so it repeated only because
its depth-3 search scored every alternative even lower: the attack had stalled
against a well-defended king. This matches the defensive agent's design.

**The defensive agent was more careful; the aggressive agent was more
accurate overall.** The defensive agent made the fewest inaccuracies (40 vs 52)
and blunders (20 vs 22), which fits its loss aversion and piece-safety terms. The
aggressive agent lost less per move in the middlegame (63 vs 68), where its
attacking terms produce purposeful moves. Both were weakest in the opening
(about 92–94), where depth 3 can't see the long-term value of development.

**Colour made little difference.** The aggressive agent scored 2.5/5 as White
and 3/5 as Black; the defensive agent 2/5 and 2.5/5. Alternating colours and
pairing the openings worked as intended.

## 4. Effect of the improvements (earlier version vs final version)

The same 10-game match was first played before the piece-square tables (PSTs)
and the search enhancements were added:

| | Earlier version | Final version |
|---|---|---|
| Score (Aggressive – Defensive) | 7 – 3 | 5.5 – 4.5 |
| Avg centipawn loss (Aggressive / Defensive) | 73 / 83 | 69 / 73 |
| Blunders (Aggressive / Defensive) | 22 / 31 | 22 / 20 |
| Avg time per move (Aggressive / Defensive) | 2.12 s / 3.49 s | 1.09 s / 1.79 s |
| Whole match | about 36 min | about 16 min |

- **The defensive agent improved most.** Its PSTs reward a compact, sheltered
  setup and penalise knights on the rim, which fixed its earlier habit of
  shuffling knights (`Nh3`, `Ng1`, `Nb1`). Its accuracy improved from 83 to 73,
  and its blunders fell from 31 to 20. Tested on its own, the PST version beat the
  old version 7–3.
- **The aggressive agent improved a little.** Its accuracy improved from 73 to 69.
  Its PSTs only helped at half strength; at full strength they tempted it into
  tactically unsound moves just past its search depth.
- **The search is about twice as fast.** That comes from the transposition
  table, iterative deepening and killer/history move ordering. It plays exactly
  the same moves in value terms (every score matches plain Minimax), but in
  about half the time.

## 5. Results against reference opponents

Each agent, at depth 3, also played 4 games against each reference opponent,
with colours alternating and the same paired openings.

| Agent | vs Greedy (1-ply lookahead) | vs Stockfish, skill 0, 0.05 s/move |
|---|---|---|
| Aggressive | **4 / 4**, all by checkmate in 15–34 plies | **2.5 / 4** (+2 =1 −1) |
| Defensive | **4 / 4**, all by checkmate in 18–34 plies | **2 / 4** (+1 =2 −1) |

- **Against greedy**, both agents win every game quickly. The greedy agent grabs
  material without considering the reply, and a depth-3 search with quiescence
  punishes that straight away. This confirms that both the search and the
  evaluations work.
- **Against weakened Stockfish**, both agents score about 50%, so they're
  competitive with a real engine at its lowest skill setting. The results match
  their styles. The aggressive agent's games were decisive (2 wins, 1 loss),
  the defensive agent's were mostly drawn (1 win, 2 draws, 1 loss).

Logs: `logs/*_aggressive_vs_greedy`, `logs/*_defensive_vs_greedy`,
`logs/*_vs_stockfish__skill_0`.

## 6. Limitations

- **Ten games is a small sample.** A 5.5–4.5 score cannot show one agent is
  stronger; the differences in *how* games were won are more reliable than the
  score.
- **Both agents search only 3 plies.** Several decisive moments (the Greek gift
  sacrifice in game 7, the pawn grab in game 10) were blunders a deeper search
  would have seen. At this depth, an evaluation's job is partly to compensate,
  which is exactly where the two strategies differ.
- **Fixed openings.** Each game starts after six book moves, so the results show
  how each strategy handles these particular positions.
