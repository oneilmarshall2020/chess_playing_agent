#Board Rendering

import os
import io
import chess
import chess.svg
import pygame

#------------------------------------------------------------------------------------------Assignments
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images") 

SQUARE = 72
BOARD_SIZE = SQUARE * 8
PANEL_WIDTH = 360
PANEL_X = BOARD_SIZE + 14
PANEL_INNER = PANEL_WIDTH - 28
PANEL_CENTRE_X = BOARD_SIZE + PANEL_WIDTH // 2
WINDOW_SIZE = (BOARD_SIZE + PANEL_WIDTH, BOARD_SIZE)

BACKGROUND = (38, 36, 33)
PANEL = (49, 46, 43)
BUTTON = (72, 69, 65)
BUTTON_HOVER = (95, 92, 87)
BUTTON_DISABLED = (58, 56, 53)
RED = (176, 48, 48)
RED_HOVER = (205, 70, 70)
TEXT = (235, 235, 235)
MUTED = (160, 160, 160)
DISABLED_TEXT = (110, 110, 110)
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

MOVES_TOP = 176
MOVES_BOTTOM = BOARD_SIZE - 58
CONTROLS_Y = MOVES_BOTTOM + 10
MOVE_ROW_HEIGHT = 22

# Colour-choice tiles on the menu: key -> image file in frontend/images/
CHOICE_NAMES = {"white": "WhiteChoice", "random": "RandomChoice", "black": "BlackChoice"}
TILE_SIZE = 64


class Button:
    """A clickable rectangle. ``label`` may be a string or a zero-arg function."""

    def __init__(self, rect, label, action, color = None, enabled = None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.color = color
        self.enabled = enabled

    def text(self):
        return self.label() if callable(self.label) else self.label

    def is_enabled(self):
        return self.enabled is None or bool(self.enabled())

#A square image button used for the colour choice (white / random / black).
class Tile(Button):
    def __init__(self, rect, key, action):
        super().__init__(rect, "", action)
        self.key = key


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
        self.choice_images = self._load_choice_images()
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

    #Load the white / random / black selection tiles from the images folder.
    def _load_choice_images(self):
        images = {}
        for key, name in CHOICE_NAMES.items():
            path = os.path.join(IMAGES_DIR, f"{name}.png")
            try:
                image = pygame.image.load(path).convert_alpha()
                images[key] = pygame.transform.smoothscale(image, (TILE_SIZE, TILE_SIZE))
            except (pygame.error, FileNotFoundError):
                images[key] = self._fallback_choice(key)
        return images

    def _fallback_choice(self, key):
        surface = pygame.Surface((TILE_SIZE, TILE_SIZE))
        fill, ink, symbol = {"white": ((20, 20, 20), (240, 240, 240), "W"),
                             "black": ((240, 240, 240), (20, 20, 20), "B"),
                             "random": ((240, 240, 240), (20, 20, 20), "?")}[key]
        surface.fill(fill)
        label = self.font_title.render(symbol, True, ink)
        surface.blit(label, label.get_rect(center=(TILE_SIZE // 2, TILE_SIZE // 2)))
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

    def _font(self, size, bold=True):
        cache = self.__dict__.setdefault("_font_cache", {})
        if (size, bold) not in cache:
            cache[(size, bold)] = pygame.font.SysFont(FONT_NAMES, size, bold=bold)
        return cache[(size, bold)]

    def fit_font(self, text, max_size, max_width, bold=True):
        for size in range(max_size, 9, -2):
            font = self._font(size, bold)
            if font.size(text)[0] <= max_width:
                return font
        return self._font(10, bold)

    def wrap_text(self, text, font, max_width):
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if font.size(trial)[0] <= max_width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines

    def text_at(self, text, font, color, pos, anchor="center"):
        image = font.render(text, True, color)
        self.screen.blit(image, image.get_rect(**{anchor: pos}))

    def draw_panel_background(self, title="Chess Agents", subtitle=""):
        pygame.draw.rect(self.screen, PANEL, (BOARD_SIZE, 0, PANEL_WIDTH, BOARD_SIZE))
        self.text_at(title, self.fit_font(title, 24, PANEL_INNER), TEXT, (PANEL_CENTRE_X, 24))
        if subtitle:
            self.text_at(subtitle, self.fit_font(subtitle, 16, PANEL_INNER, bold=False), MUTED,
                         (PANEL_CENTRE_X, 50))

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
            enabled = button.is_enabled()
            hovered = enabled and button.rect.collidepoint(mouse_pos)
            if not enabled:
                fill, ink = BUTTON_DISABLED, DISABLED_TEXT
            else:
                normal, hover = button.color or (BUTTON, BUTTON_HOVER)
                fill, ink = (hover if hovered else normal), TEXT
            pygame.draw.rect(self.screen, fill, button.rect, border_radius=6)
            self.text(button.text(), self.font_bold, ink, button.rect.center, center=True)

    #Colour-choice tiles: the selected one is bright with a green border, the rest are dimmed.
    def draw_tiles(self, tiles, selected_key, mouse_pos):
        for tile in tiles:
            self.screen.blit(self.choice_images[tile.key], tile.rect)
            if tile.key != selected_key:
                dim = pygame.Surface(tile.rect.size, pygame.SRCALPHA)
                dim.fill((0, 0, 0, 50 if tile.rect.collidepoint(mouse_pos) else 130))
                self.screen.blit(dim, tile.rect)
            if tile.key == selected_key:
                pygame.draw.rect(self.screen, ACCENT, tile.rect.inflate(6, 6), width=3, border_radius=4)
            else:
                pygame.draw.rect(self.screen, BUTTON, tile.rect.inflate(6, 6), width=1, border_radius=4)
            caption = {"white": "White", "random": "Random", "black": "Black"}[tile.key]
            self.text(caption, self.font_small, TEXT if tile.key == selected_key else MUTED,
                        (tile.rect.centerx, tile.rect.bottom + 12), center=True)

    ##   Status box; shows a sliding bar while an agent is thinking.
    def draw_status(self, headline, detail, thinking, think_phase, top=284):
        box = pygame.Rect(PANEL_X, top, PANEL_INNER, 62)
        pygame.draw.rect(self.screen, BACKGROUND, box, border_radius=6)
        self.text(headline, self.font_bold, ACCENT if thinking else TEXT, (box.x + 10, box.y + 8))
        self.text(detail, self.font, MUTED, (box.x + 10, box.y + 30))

    @staticmethod
    def move_list_area():
        return pygame.Rect(PANEL_X, MOVES_TOP + 22, PANEL_INNER, MOVES_BOTTOM - MOVES_TOP - 22)

    @classmethod
    def visible_rows(cls):
        return max(1, (cls.move_list_area().h - 8) // MOVE_ROW_HEIGHT)

    #Two-column move list; the displayed move is highlighted.
    def draw_move_list(self, san_moves, shown_ply, start_row):
        self.text("Moves", self.font_bold, MUTED, (PANEL_X, MOVES_TOP))
        area = self.move_list_area()
        pygame.draw.rect(self.screen, BACKGROUND, area, border_radius=6)
        visible = self.visible_rows()
        rows = (len(san_moves) + 1) // 2
        for row in range(start_row, min(rows, start_row + visible)):
            y = area.y + 6 + (row - start_row) * MOVE_ROW_HEIGHT
            self.text(f"{row + 1}.", self.font, MUTED, (area.x + 8, y))
            for column in (0, 1):
                ply = row * 2 + column
                if ply < len(san_moves):
                    x = area.x + 50 + column * 130
                    if ply + 1 == shown_ply:
                        pygame.draw.rect(self.screen, BUTTON, (x - 4, y - 2, 90, MOVE_ROW_HEIGHT - 1), border_radius=4)
                    self.text(san_moves[ply], self.font_bold, TEXT, (x, y))
        if rows > visible:                              # scroll bar
            track = pygame.Rect(area.right - 8, area.y + 4, 4, area.h - 8)
            pygame.draw.rect(self.screen, BUTTON, track, border_radius=2)
            thumb_h = max(20, int(track.h * visible / rows))
            thumb_y = track.y + int((track.h - thumb_h) * start_row / (rows - visible))
            pygame.draw.rect(self.screen, MUTED, (track.x, thumb_y, track.w, thumb_h), border_radius=2)
