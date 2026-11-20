"""Aggressive agent: evaluation function and strategy.

Strategic identity (plain language)
-----------------------------------
"Prioritises piece activity, initiative and attacking the enemy king; keeps
pieces on the board and avoids draws."

Where the defensive agent asks "is my position safe?", this agent asks "how
much pressure am I putting on the opponent?". Concretely, on top of material:

  * Activity      - pieces score for every square they control (mobility)
                    and for standing in the enemy half of the board.
  * King attack   - pieces bearing on the squares around the enemy king score
                    "attack units"; the bonus grows with the SQUARE of the
                    units and only counts once 2+ pieces join the attack
                    (one piece alone rarely mates). Queens/rooks/knights also
                    score for being close to the enemy king (tropism), rooks
                    and queens for open files towards it, and pawns for
                    storming up the files in front of it.
  * Threats       - attacking an enemy piece with a cheaper piece (initiative:
                    the opponent must spend a move reacting). Giving check
                    scores too.
  * Initiative    - this agent counts its OWN attacking terms 1.3x and the
                    opponent's 1.0x, i.e. it values its attack more than it
                    fears the counter-attack (the mirror image of the
                    defensive agent's loss aversion).
  * Keep tension  - a bonus for the amount of non-pawn material still on the
                    board, so it avoids trading pieces off (the defensive
                    agent does the opposite when ahead).
  * King hunt     - in the endgame, when ahead, it drives the enemy king to
                    the edge and brings its own king closer, so it converts
                    wins instead of shuffling.
  * Contempt      - a draw is scored as -0.5 pawns for this agent, so it
                    avoids repetitions unless it is actually losing.
  * Piece-square  - a bonus/penalty for every piece on every square (PSTs),
    tables          written for an ATTACKING style: pawns are worth far more
                    the further they advance, knights want outposts in the
                    enemy half (and avoid the rim), rooks want the 7th rank.
                    The king uses two tables blended by game phase ("tapered"):
                    sheltered while queens and rooks are on, central in the
                    endgame so it can join the attack.

Everything is computed from White's point of view (positive = good for
White), as required by backend/engine.py.
"""

import chess

from backend.base import DEFAULT_DEPTH
from backend.engine import PIECE_VALUES, MinimaxAgent

# ------------------------------------------------------------------ weights
# All values are centipawns (100 = one pawn).

MOBILITY_WEIGHT = {chess.KNIGHT: 4, chess.BISHOP: 4, chess.ROOK: 2, chess.QUEEN: 1}
ENEMY_HALF_BONUS = 8            # per minor/major piece standing in the enemy half

ATTACK_UNITS = {chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 3, chess.QUEEN: 5}
KING_ATTACK_SCALE = 2           # bonus = scale * units^2 ...
KING_ATTACK_CAP = 450           # ... capped so it never outweighs a queen
MIN_KING_ATTACKERS = 2
# Per square closer to the enemy king. The queen is kept low: at 5 it made ~30% of the
# agent's opening moves queen sorties (Qh4, Qc4, Qg4 ...); at 2 it is ~14%, and lower
# values didn't reduce it further (measured over 16 games vs the defensive agent).
TROPISM_WEIGHT = {chess.QUEEN: 2, chess.ROOK: 2, chess.KNIGHT: 3}
OPEN_FILE_TO_KING = 25          # rook/queen on a file at the enemy king without our pawns
PAWN_STORM = 8                  # per rank a pawn has advanced towards the enemy king

THREAT_DIVISOR = 6              # attacking a piece: (victim - attacker) / divisor
CHECK_BONUS = 30

INITIATIVE = 1.3                # weight on OUR attacking terms (opponent's = 1.0)
TENSION_DIVISOR = 40            # bonus = non-pawn material on board / divisor
CONTEMPT = 50                   # a draw counts as -50 for this agent

ENDGAME_MATERIAL = 1300         # enemy non-pawn material at/below this = endgame
WINNING_MARGIN = 200            # must be 2 pawns ahead to start the king hunt
EDGE_WEIGHT = 10                # per step the enemy king is from the centre
KING_CHASE_WEIGHT = 4           # per step our king is closer to the enemy king

ATTACKING_PIECES = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)

# ------------------------------------------------------- piece-square tables
# Written from WHITE's point of view, laid out like the board seen by White:
# the first row is rank 8, the last row is rank 1 (a-file on the left).
# Black uses the same tables mirrored vertically, so the evaluation stays
# colour-symmetric. Values in centipawns, added on top of material.

PAWN_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
    80,  80,  80,  80,  80,  80,  80,  80,    # one step from queening
    30,  30,  40,  50,  50,  40,  30,  30,
    10,  10,  20,  35,  35,  20,  10,  10,    # advanced centre pawns gain space
     5,   5,  10,  25,  25,  10,   5,   5,
     0,   0,   0,   5,   5,  -5,   0,   0,    # f3 weakens the king
     0,   0,   0, -20, -20,   5,   5,   5,    # unmoved d/e pawns block the pieces
     0,   0,   0,   0,   0,   0,   0,   0,
]
KNIGHT_TABLE = [
   -50, -30, -20, -20, -20, -20, -30, -50,
   -20,   0,  15,  20,  20,  15,   0, -20,
   -10,  15,  25,  30,  30,  25,  15, -10,    # outposts deep in enemy territory
   -10,  10,  20,  30,  30,  20,  10, -10,
   -15,   0,  15,  20,  20,  15,   0, -15,
   -20,   0,  10,  10,  10,  10,   0, -20,    # "a knight on the rim is dim" (Na3/Nh3)
   -30, -15,   0,   5,   5,   0, -15, -30,
   -50, -35, -25, -25, -25, -25, -35, -50,
]
BISHOP_TABLE = [
   -20, -10, -10, -10, -10, -10, -10, -20,
   -10,   5,   0,   0,   0,   0,   5, -10,
   -10,  10,  10,  10,  10,  10,  10, -10,
   -10,   5,  15,  15,  15,  15,   5, -10,
   -10,  10,  10,  15,  15,  10,  10, -10,
   -10,   5,  10,  10,  10,  10,   5, -10,
   -10,  10,   0,   5,   5,   0,  10, -10,    # fianchetto / long diagonals
   -20, -10, -15, -10, -10, -15, -10, -20,
]
ROOK_TABLE = [
     5,  10,  10,  15,  15,  10,  10,   5,
    25,  30,  30,  30,  30,  30,  30,  25,    # rook on the 7th rank
     0,   5,   5,   5,   5,   5,   5,   0,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   5,  10,  10,   5,   0,   0,    # central files after castling
]
QUEEN_TABLE = [
   -20, -10, -10,  -5,  -5, -10, -10, -20,
   -10,   0,   5,   5,   5,   5,   0, -10,
   -10,   5,   5,   5,   5,   5,   5, -10,
    -5,   0,   5,   5,   5,   5,   0,  -5,
    -5,   0,   5,   5,   5,   5,   0,  -5,
   -10,   0,   5,   5,   5,   5,   0, -10,
   -10,   0,   0,   0,   0,   0,   0, -10,
   -20, -10, -10,  -5,  -5, -10, -10, -20,    # mild: the queen's activity comes from the attack terms
]
KING_MIDDLEGAME_TABLE = [
   -40, -40, -40, -50, -50, -40, -40, -40,
   -40, -40, -40, -50, -50, -40, -40, -40,
   -40, -40, -40, -50, -50, -40, -40, -40,
   -40, -40, -40, -50, -50, -40, -40, -40,
   -30, -30, -30, -40, -40, -30, -30, -30,
   -20, -20, -20, -20, -20, -20, -20, -20,
    10,  10,   0,   0,   0,   0,  10,  10,
    20,  30,  10,   0,   0,  10,  30,  20,    # castled
]
KING_ENDGAME_TABLE = [
   -50, -30, -20, -20, -20, -20, -30, -50,
   -30, -10,   0,  10,  10,   0, -10, -30,
   -20,   0,  20,  30,  30,  20,   0, -20,
   -20,  10,  30,  40,  40,  30,  10, -20,    # an active king in the centre
   -20,  10,  30,  40,  40,  30,  10, -20,
   -20,   0,  20,  30,  30,  20,   0, -20,
   -30, -10,   0,   0,   0,   0, -10, -30,
   -50, -30, -30, -30, -30, -30, -30, -50,
]
PIECE_TABLES = {chess.PAWN: PAWN_TABLE, chess.KNIGHT: KNIGHT_TABLE, chess.BISHOP: BISHOP_TABLE,
                chess.ROOK: ROOK_TABLE, chess.QUEEN: QUEEN_TABLE}
FULL_NON_PAWN_MATERIAL = 6400   # both sides' knights, bishops, rooks and queens at the start
# Scale of the whole piece-square score. Tuned against the agent without PSTs (10 games
# each, depth 2, moves graded by Stockfish): at 1.0 the tables tempted it into moves whose
# tactical cost lay just past its horizon (more blunders than without PSTs); at 0.5 and
# 0.25 it scored 5.5/10 and 6/10 with fewer blunders (38 vs 43, 33 vs 38).
PST_WEIGHT = 0.5


def _by_square(table):
    """Re-index a table written as seen by White (rank 8 first) by square,
    for (White, Black). White's a1 is row 8 of the table; Black's a8 is the
    same entry, mirrored."""
    white = [table[chess.square_mirror(square)] for square in chess.SQUARES]
    black = [table[square] for square in chess.SQUARES]
    return white, black


PST = {piece_type: _by_square(table) for piece_type, table in PIECE_TABLES.items()}
KING_PST_MIDDLEGAME = _by_square(KING_MIDDLEGAME_TABLE)
KING_PST_ENDGAME = _by_square(KING_ENDGAME_TABLE)


def _squares(mask: int):
    """Iterate over the squares set in a bitboard."""
    return chess.scan_forward(mask)


def _centre_distance(square: int) -> int:
    """0 for the four centre squares, up to 6 for a corner."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    return max(3 - file, file - 4) + max(3 - rank, rank - 4)


class AggressiveAgent(MinimaxAgent):
    """Aggressive agent: the shared Minimax search + the eval."""

    def __init__(self, depth: int = DEFAULT_DEPTH):
        super().__init__("Aggressive", self.evaluate_board_state, depth, contempt=CONTEMPT)
        self.color = chess.WHITE        # the side we play; set before every search

    def choose_move(self, board: chess.Board) -> chess.Move:
        self.color = board.turn
        return super().choose_move(board)

    # ------------------------------------------------------------ evaluation
    def evaluate_board_state(self, board: chess.Board) -> float:
        """Score ``board`` from White's point of view (centipawns)."""
        score = 0.0
        for color in (chess.WHITE, chess.BLACK):
            sign = 1 if color == chess.WHITE else -1
            weight = INITIATIVE if color == self.color else 1.0
            attack = (self._activity_and_king_attack(board, color)
                      + self._threats(board, color))
            score += sign * (self._material(board, color) + weight * attack)
        score += PST_WEIGHT * self._piece_squares(board)

        if board.is_check():                    # side to move is in check
            score += -CHECK_BONUS if board.turn == chess.WHITE else CHECK_BONUS

        own = 1 if self.color == chess.WHITE else -1
        score += own * (self._tension(board) + self._king_hunt(board))
        return int(score)

    # ---------------------------------------------------------------- terms
    @staticmethod
    def _material(board: chess.Board, color: chess.Color) -> int:
        return sum(PIECE_VALUES[pt] * chess.popcount(board.pieces_mask(pt, color))
                   for pt in PIECE_VALUES)

    @staticmethod
    def _piece_squares(board: chess.Board) -> float:
        """Piece-square table score, White minus Black.

        The king's table is tapered: weighted towards the middlegame table
        while lots of material is on the board, and towards the endgame table
        as pieces are traded (phase 1.0 = all pieces, 0.0 = only kings/pawns).
        """
        non_pawn = sum(PIECE_VALUES[pt] * chess.popcount(board.pieces_mask(pt, c))
                       for pt in ATTACKING_PIECES for c in chess.COLORS)
        phase = min(1.0, non_pawn / FULL_NON_PAWN_MATERIAL)
        score = 0.0
        for color, index, sign in ((chess.WHITE, 0, 1), (chess.BLACK, 1, -1)):
            for piece_type, tables in PST.items():
                table = tables[index]
                for square in _squares(board.pieces_mask(piece_type, color)):
                    score += sign * table[square]
            king = board.king(color)
            if king is not None:
                score += sign * (phase * KING_PST_MIDDLEGAME[index][king]
                                 + (1 - phase) * KING_PST_ENDGAME[index][king])
        return score

    @staticmethod
    def _activity_and_king_attack(board: chess.Board, color: chess.Color) -> float:
        """Mobility, advanced pieces, and pressure on the enemy king.

        One pass over our pieces computes all of these, because the
        evaluation runs thousands of times per move.
        """
        enemy_king = board.king(not color)
        own_pieces = board.occupied_co[color]
        enemy_half = chess.BB_RANK_5 | chess.BB_RANK_6 | chess.BB_RANK_7 | chess.BB_RANK_8
        if color == chess.BLACK:
            enemy_half = chess.BB_RANK_1 | chess.BB_RANK_2 | chess.BB_RANK_3 | chess.BB_RANK_4
        king_zone = (chess.BB_KING_ATTACKS[enemy_king] | chess.BB_SQUARES[enemy_king]
                     if enemy_king is not None else 0)

        score = 0
        units = attackers = 0
        for piece_type in ATTACKING_PIECES:
            for square in _squares(board.pieces_mask(piece_type, color)):
                attacks = board.attacks_mask(square)
                score += MOBILITY_WEIGHT[piece_type] * chess.popcount(attacks & ~own_pieces)
                if chess.BB_SQUARES[square] & enemy_half:
                    score += ENEMY_HALF_BONUS
                if enemy_king is None:
                    continue
                hits = chess.popcount(attacks & king_zone)
                if hits:
                    attackers += 1
                    units += hits * ATTACK_UNITS[piece_type]
                if piece_type in TROPISM_WEIGHT:
                    score += (7 - chess.square_distance(square, enemy_king)) * TROPISM_WEIGHT[piece_type]

        if enemy_king is None:
            return score
        if attackers >= MIN_KING_ATTACKERS:
            score += min(KING_ATTACK_CAP, KING_ATTACK_SCALE * units * units)

        # Open lines and pawn storm on the three files around the enemy king.
        king_file = chess.square_file(enemy_king)
        our_pawns = board.pieces_mask(chess.PAWN, color)
        heavy = board.pieces_mask(chess.ROOK, color) | board.pieces_mask(chess.QUEEN, color)
        for file in range(max(0, king_file - 1), min(7, king_file + 1) + 1):
            file_mask = chess.BB_FILES[file]
            if heavy & file_mask and not our_pawns & file_mask:
                score += OPEN_FILE_TO_KING
            for pawn in _squares(our_pawns & file_mask):
                rank = chess.square_rank(pawn)
                advanced = rank if color == chess.WHITE else 7 - rank   # 1 = start rank
                if advanced >= 3:
                    score += (advanced - 2) * PAWN_STORM
        return score

    @staticmethod
    def _threats(board: chess.Board, color: chess.Color) -> float:
        """Reward attacking enemy pieces with cheaper pieces."""
        score = 0
        targets = board.occupied_co[not color] & ~board.kings
        our_non_kings = board.occupied_co[color] & ~board.kings
        for square in _squares(targets):
            attackers = board.attackers_mask(color, square) & our_non_kings
            if not attackers:
                continue
            victim = PIECE_VALUES[board.piece_type_at(square)]
            cheapest = min(PIECE_VALUES[board.piece_type_at(a)] for a in _squares(attackers))
            if cheapest < victim:
                score += (victim - cheapest) / THREAT_DIVISOR
        return score

    @staticmethod
    def _tension(board: chess.Board) -> float:
        """Bonus for keeping pieces (not pawns) on the board: avoid trades."""
        non_pawn = sum(PIECE_VALUES[pt] * chess.popcount(board.pieces_mask(pt, c))
                       for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
                       for c in (chess.WHITE, chess.BLACK))
        return non_pawn / TENSION_DIVISOR

    def _king_hunt(self, board: chess.Board) -> float:
        """Endgame: when clearly ahead, push the enemy king to the edge."""
        us, them = self.color, not self.color
        enemy_pieces = sum(PIECE_VALUES[pt] * chess.popcount(board.pieces_mask(pt, them))
                           for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))
        if enemy_pieces > ENDGAME_MATERIAL:
            return 0
        lead = self._material(board, us) - self._material(board, them)
        our_king, enemy_king = board.king(us), board.king(them)
        if lead < WINNING_MARGIN or our_king is None or enemy_king is None:
            return 0
        return (EDGE_WEIGHT * _centre_distance(enemy_king)
                + KING_CHASE_WEIGHT * (14 - chess.square_manhattan_distance(our_king, enemy_king)))
