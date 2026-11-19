#Board Rendering

import os
import io
import chess
import chess.svg
import pygame

#------------------------------------------------------------------------------------------Assignments
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SQUARE = 72
BOARD_SIZE = SQUARE * 8
PANEL_WIDTH = 360
PANEL_X = BOARD_SIZE + 14
PANEL_INNER = PANEL_WIDTH - 28
WINDOW_SIZE = (BOARD_SIZE + PANEL_WIDTH, BOARD_SIZE)

BACKGROUND = (38, 36, 33)
PANEL = (49, 46, 43)
BUTTON = (72, 69, 65)
BUTTON_HOVER = (95, 92, 87)
TEXT = (235, 235, 235)
MUTED = (160, 160, 160)
ACCENT = (129, 182, 76)
LIGHT_SQ = (240, 217, 181)
DARK_SQ = (181, 136, 99)
LAST_MOVE_HL = (205, 210, 106, 140)
SELECTED_HL = (246, 246, 105, 160)
CHECK_HL = (230, 60, 60, 170)
HINT = (90, 90, 90)

PROMOTION_PIECES = (chess.QUEEN, chess.ROOK, chess.KNIGHT, chess.BISHOP)
PIECE_SYMBOLS = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
                 chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}

FONT_NAMES = "segoeui,helvetica,arial"


class Button:
    """A clickable rectangle. ``label`` may be a string or a zero-arg function."""

    def __init__(self, rect, label, action):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action

    def text(self):
        return self.label() if callable(self.label) else self.label

#Pygame window and drawings/renderings
class BoardView:

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Chess using Minimax with Alpha-Beta Pruning")
        self.font_title = pygame.font.SysFont(FONT_NAMES, 24, bold=True)
        self.font_big = pygame.font.SysFont(FONT_NAMES, 44, bold=True)
        self.font = pygame.font.SysFont(FONT_NAMES, 16)
        self.font_bold = pygame.font.SysFont(FONT_NAMES, 16, bold=True)
        self.font_small = pygame.font.SysFont(FONT_NAMES, 12, bold=True)
        self.images = self._load_images()
        self._backgrounds = {}

    # ------------------------------------------------------------ assets
    
    #Loads the 12 piece PNGs (frontend/images/wP.png ...), with fallbacks.
    def _load_images(self):
        images = {}
        for piece_type, symbol in PIECE_SYMBOLS.items():
            for color, letter in ((chess.WHITE, "w"), (chess.BLACK, "b")):
                path = os.path.join(BASE_DIR, "images", f"{letter}{symbol}.png")
                try:
                    image = pygame.image.load(path).convert_alpha()
                    images[(piece_type, color)] = pygame.transform.smoothscale(image, (SQUARE, SQUARE))
                except (pygame.error, FileNotFoundError):
                    images[(piece_type, color)] = self._fallback_piece(symbol, color)
        return images

    #Allows a lettered disk to be used when the image for piece is missing or fails to load
    def _fallback_piece(self, symbol, color):
        surface = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        fill, ink = ((250, 250, 250), (20, 20, 20)) if color == chess.WHITE else ((40, 40, 40), (240, 240, 240))
        center = (SQUARE // 2, SQUARE // 2)
        pygame.draw.circle(surface, fill, center, SQUARE // 2 - 8)
        pygame.draw.circle(surface, ink, center, SQUARE // 2 - 8, 2)
        label = self.font_title.render(symbol, True, ink)
        surface.blit(label, label.get_rect(center=center))
        return surface

    #Uses board squares from chess.svg. Plain squares if SVG fails to render.
    def _background(self, flipped):
        if flipped not in self._backgrounds:
            try:
                svg = chess.svg.board(size=BOARD_SIZE, coordinates=False,
                                      orientation=chess.BLACK if flipped else chess.WHITE)
                surface = pygame.image.load(io.BytesIO(svg.encode()), "board.svg").convert()
            except pygame.error:
                surface = pygame.Surface((BOARD_SIZE, BOARD_SIZE))
                for row in range(8):
                    for col in range(8):
                        color = LIGHT_SQ if (row + col) % 2 == 0 else DARK_SQ
                        pygame.draw.rect(surface, color, (col * SQUARE, row * SQUARE, SQUARE, SQUARE))
            self._backgrounds[flipped] = surface
        return self._backgrounds[flipped]

    # ------------------------------------------------------- coordinates
    
    #Top-left pixel of a square.
    @staticmethod
    def square_to_xy(square, flipped):
        file, rank = chess.square_file(square), chess.square_rank(square)
        if flipped:
            return (7 - file) * SQUARE, rank * SQUARE
        return file * SQUARE, (7 - rank) * SQUARE

    #Square under a pixel, or None if off the board.
    @staticmethod
    def xy_to_square(pos, flipped):
        x, y = pos
        if not (0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
            return None
        file, rank = x // SQUARE, 7 - y // SQUARE
        if flipped:
            file, rank = 7 - file, 7 - rank
        return chess.square(file, rank)

    #Clickable squares for the promotion picker, centred on the board.
    @staticmethod
    def promotion_rects():
        left = BOARD_SIZE // 2 - 2 * SQUARE
        return [(p, pygame.Rect(left + i * SQUARE, BOARD_SIZE // 2 - SQUARE // 2, SQUARE, SQUARE))
                for i, p in enumerate(PROMOTION_PIECES)]

    # ----------------------------------------------------------- drawing
    def text(self, text, font, color, pos, center=False):
        image = font.render(text, True, color)
        rect = image.get_rect(center=pos) if center else image.get_rect(topleft=pos)
        self.screen.blit(image, rect)

    def _tint(self, square, color, flipped):
        overlay = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        overlay.fill(color)
        self.screen.blit(overlay, self.square_to_xy(square, flipped))

    def draw_board(self, shown, flipped, last_move=None, selected=None, targets=(),
                   drag_square=None, mouse_pos=(0, 0), promo_color=None):

        self.screen.blit(self._background(flipped), (0, 0))

        for square in chess.SQUARES:                    # rank / file labels
            x, y = self.square_to_xy(square, flipped)
            on_light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            ink = DARK_SQ if on_light else LIGHT_SQ
            if x == 0:
                self.text(str(chess.square_rank(square) + 1), self.font_small, ink, (x + 3, y + 2))
            if y == BOARD_SIZE - SQUARE:
                self.text(chess.FILE_NAMES[chess.square_file(square)], self.font_small, ink,
                          (x + SQUARE - 11, y + SQUARE - 16))

        if last_move:
            self._tint(last_move.from_square, LAST_MOVE_HL, flipped)
            self._tint(last_move.to_square, LAST_MOVE_HL, flipped)
        if shown.is_check():
            self._tint(shown.king(shown.turn), CHECK_HL, flipped)
        if selected is not None:
            self._tint(selected, SELECTED_HL, flipped)
            for square, is_capture in targets:
                cx, cy = (v + SQUARE // 2 for v in self.square_to_xy(square, flipped))
                if is_capture:
                    pygame.draw.circle(self.screen, HINT, (cx, cy), SQUARE // 2 - 4, 4)
                else:
                    pygame.draw.circle(self.screen, HINT, (cx, cy), 9)

        for square, piece in shown.piece_map().items():
            if square == drag_square:
                continue
            self.screen.blit(self.images[(piece.piece_type, piece.color)], self.square_to_xy(square, flipped))
        if drag_square is not None:
            piece = shown.piece_at(drag_square)
            if piece:
                image = self.images[(piece.piece_type, piece.color)]
                self.screen.blit(image, image.get_rect(center=mouse_pos))

        if promo_color is not None:
            shade = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            self.screen.blit(shade, (0, 0))
            for piece_type, rect in self.promotion_rects():
                hovered = rect.collidepoint(mouse_pos)
                pygame.draw.rect(self.screen, (230, 230, 230) if hovered else (190, 190, 190), rect, border_radius=8)
                self.screen.blit(self.images[(piece_type, promo_color)], rect)

    def draw_buttons(self, buttons, mouse_pos):
        for button in buttons:
            hovered = button.rect.collidepoint(mouse_pos)
            pygame.draw.rect(self.screen, BUTTON_HOVER if hovered else BUTTON, button.rect, border_radius=6)
            self.text(button.text(), self.font_bold, TEXT, button.rect.center, center=True)

    def draw_panel_background(self, title="Chess Agent"):
        pygame.draw.rect(self.screen, PANEL, (BOARD_SIZE, 0, PANEL_WIDTH, BOARD_SIZE))
        self.text(title, self.font_title, TEXT, (PANEL_X, 10))

    """def draw_status(self, headline, detail, thinking, think_phase, top=284):
    #   Status box; shows a sliding bar while an agent is thinking.
        box = pygame.Rect(PANEL_X, top, PANEL_INNER, 62)
        pygame.draw.rect(self.screen, BACKGROUND, box, border_radius=6)
        self.text(headline, self.font_bold, ACCENT if thinking else TEXT, (box.x + 10, box.y + 8))
        self.text(detail, self.font, MUTED, (box.x + 10, box.y + 30))
        if thinking:
            bar = pygame.Rect(box.x + 10, box.bottom - 9, box.w - 20, 4)
            pygame.draw.rect(self.screen, BUTTON, bar, border_radius=2)
            t = think_phase % 2
            slider = pygame.Rect(bar.x + int((t if t <= 1 else 2 - t) * (bar.w - 60)), bar.y, 60, 4)
            pygame.draw.rect(self.screen, ACCENT, slider, border_radius=2)"""


    #Two-column move list; the displayed move is highlighted.
    def draw_move_list(self, san_moves, shown_ply, top=358):
        self.text("Moves", self.font_bold, MUTED, (PANEL_X, top))
        area = pygame.Rect(PANEL_X, top + 24, PANEL_INNER, BOARD_SIZE - top - 34)
        pygame.draw.rect(self.screen, BACKGROUND, area, border_radius=6)
        row_height = 20
        visible = area.h // row_height
        rows = (len(san_moves) + 1) // 2
        target = max(0, (shown_ply - 1) // 2)
        start = max(0, min(target - visible + 1, rows - visible)) if rows > visible else 0
        for row in range(start, min(rows, start + visible)):
            y = area.y + (row - start) * row_height + 2
            self.text(f"{row + 1}.", self.font, MUTED, (area.x + 8, y))
            for column in (0, 1):
                ply = row * 2 + column
                if ply < len(san_moves):
                    x = area.x + 50 + column * 130
                    if ply + 1 == shown_ply:
                        pygame.draw.rect(self.screen, BUTTON, (x - 4, y - 1, 90, row_height - 1), border_radius=4)
                    self.text(san_moves[ply], self.font_bold, TEXT, (x, y))
