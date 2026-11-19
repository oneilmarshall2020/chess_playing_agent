#Holds eval function
import os
import sys

# Put the project root (the folder containing backend/ and frontend/) on sys.path so the
# `backend.` imports work no matter where this file is run or imported from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from backend.base import DEFAULT_DEPTH
from backend.engine import MinmaxAgent, PIECE_VALUES

LOSS_AVERSION = 1.15            # weight on our own material (opponent's counts 1.0)
LEAD_THRESHOLD = 200            # "ahead" = at least two pawns up
START_NON_PAWN = 6400           # non-pawn material on the board at the start (both sides)

#----------------------------------------------------------------------------------------------- Code 

#King attacking a piece is last priority, hence king recieves a big value.
#Agent avoids making a move that would endager the King, even if it loses a less valued piece.

def _attacker_value(piece_type):
    return 10_000 if piece_type == chess.KING else PIECE_VALUES[piece_type]



#Main defensive Agent class, inherits Minmax Class and uses the eval function for the board state.
#Eval function is designed to be loss averse. Rewards piece protection, pawn structure, king safety and development. 
#Penalizes hanging pieces, doubled pawns, isolated pawns and losing exchanges.

class DefensiveAgent(MinmaxAgent):
    """Defensive agent: the shared engine search + this file's evaluation function."""

    def __init__(self, depth=DEFAULT_DEPTH):
        super().__init__("Defensive", self.evaluate_board_state, depth)
        self.color = chess.WHITE        # the side we are playing; set at the start of each search

    def choose_move(self, board):
        self.color = board.turn
        return super().choose_move(board)

    # ------------------------------------------------------------ Board evaluation
    #Score board from White's point of view (centipawns); see the engine's score convention.

    def evaluate_board_state(self, board):
        score = 0.0
        for color in (chess.WHITE, chess.BLACK):
            sign = 1 if color == chess.WHITE else -1
            weight = LOSS_AVERSION if color == self.color else 1.0
            score += sign * (weight * self._material(board, color)
                             + self._king_safety(board, color)
                             + self._pawn_structure(board, color)
                             + self._piece_safety(board, color)
                             + self._development(board, color))
        score += self._simplification_bonus(board)
        return int(score)

    @staticmethod
    def _material(board, color):
        return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == color)

    @staticmethod
    def _king_safety(board, color):
        king = board.king(color)
        if king is None:
            return 0
        kf, kr = chess.square_file(king), chess.square_rank(king)
        home, step = (0, 1) if color == chess.WHITE else (7, -1)
        score = 40 if (kr == home and kf in (1, 2, 6)) else 0          # tucked away on a castled square

        for f in range(max(0, kf - 1), min(7, kf + 1) + 1):             # pawn shield on the 3 files in front
            for dist, bonus in ((1, 15), (2, 8)):
                r = kr + step * dist
                if 0 <= r <= 7:
                    p = board.piece_at(chess.square(f, r))
                    if p and p.piece_type == chess.PAWN and p.color == color:
                        score += bonus
                        break
            else:
                score -= 12                                             # no shield pawn on this file

        enemy = not color                                               # enemy pressure around the king
        for sq in list(board.attacks(king)) + [king]:
            score -= 6 * len(board.attackers(enemy, sq))
        return score

    @staticmethod
    def _pawn_structure(board, color):
        pawns = board.pieces(chess.PAWN, color)
        files = [chess.square_file(s) for s in pawns]
        score = 0
        for sq in pawns:
            f = chess.square_file(sq)
            if files.count(f) > 1:
                score -= 10                                             # doubled
            if not any(abs(f - g) == 1 for g in files):
                score -= 12                                             # isolated
            if board.attackers(color, sq) & pawns:
                score += 8                                              # protected by another pawn
        return score

    @staticmethod
    def _piece_safety(board, color):
        score = 0
        for sq, piece in board.piece_map().items():
            if piece.color != color or piece.piece_type == chess.KING:
                continue
            defenders = board.attackers(color, sq)
            if defenders:
                score += 3                                              # protected pieces are good
            attackers = board.attackers(not color, sq)
            if not attackers:
                continue
            value = PIECE_VALUES[piece.piece_type]
            cheapest = min(_attacker_value(board.piece_type_at(a)) for a in attackers)
            if not defenders:
                score -= 0.5 * value                                    # hanging
            elif cheapest < value:
                score -= 0.5 * (value - cheapest)                       # losing exchange
        return score

    @staticmethod
    def _development(board, color):
        home = 0 if color == chess.WHITE else 7
        minors = board.pieces(chess.KNIGHT, color) | board.pieces(chess.BISHOP, color)
        return 8 * sum(1 for sq in minors if chess.square_rank(sq) != home)

    #If more pieces ahead, rewards for trading pieces off the board for simplification.
    def _simplification_bonus(self, board):
        mine = self._material(board, self.color)
        theirs = self._material(board, not self.color)
        if mine - theirs < LEAD_THRESHOLD:
            return 0
        non_pawn = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values()
                       if p.piece_type not in (chess.PAWN, chess.KING))
        bonus = max(0, START_NON_PAWN - non_pawn) // 20
        return bonus if self.color == chess.WHITE else -bonus