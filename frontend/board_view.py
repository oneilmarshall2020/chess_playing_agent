#Board Rendering

# Sharp on Retina / HiDPI screens:
#   The window is opened with allow_high_dpi, so on a Retina Mac the drawing surface has
#   2x the pixels of the window. Everything OUTSIDE this file (app.py, mouse positions,
#   button rects, SQUARE, PANEL_X ...) stays in normal "logical" pixels; BoardView multiplies
#   by self.scale only at the moment it draws. Fonts, pieces and images are created at the
#   full physical resolution, so nothing is stretched.

import io
import os

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
SELECTED_HL = (246, 246, 105, 160)
CHECK_HL = (230, 60, 60, 170)
HINT = (60, 60, 60, 110)
EVAL_WHITE = (238, 238, 238)
EVAL_BLACK = (20, 20, 20)
EVAL_BAR_WIDTH = 10                 # fits in the gap between the board and the panel

# Board themes: square colours, and the colour of the last-move highlight
# (also used for the current move in the move list). Cycle with the menu
# button or the T key.
THEMES = [
    {"name": "Classic", "light": (240, 217, 181), "dark": (181, 136, 99),  "last": (155, 199, 0, 140)},
    {"name": "Green",   "light": (238, 238, 210), "dark": (118, 150, 86),  "last": (246, 246, 105, 190)},
    {"name": "Ocean",   "light": (222, 227, 230), "dark": (140, 162, 173), "last": (80, 170, 255, 140)},
    {"name": "Purple",  "light": (232, 224, 245), "dark": (136, 119, 183), "last": (255, 170, 60, 160)},
    {"name": "Coral",   "light": (240, 235, 230), "dark": (205, 120, 110), "last": (90, 200, 170, 160)},
    {"name": "Slate",   "light": (200, 204, 208), "dark": (96, 108, 118),  "last": (255, 215, 80, 150)},
]

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


#A font measured in logical pixels but rendered at the screen's physical resolution.
#size() is used by app.py for layout, so it must report logical pixels.
class Font:
    def __init__(self, size, bold, scale):
        self.scale = scale
        self.real = pygame.font.SysFont(FONT_NAMES, round(size * scale), bold=bold)

    def size(self, text):
        width, height = self.real.size(text)
        return round(width / self.scale), round(height / self.scale)

    def render(self, text, antialias, color):
        return self.real.render(text, antialias, color)


#Pygame window and drawings/renderings
class BoardView:

    def __init__(self):
        pygame.init()
        try:
            # allow_high_dpi: on Retina the surface gets 2x the window's pixels
            self.window = pygame.Window("Chess using Minimax with Alpha-Beta Pruning",
                                        WINDOW_SIZE, allow_high_dpi=True)
            self.screen = self.window.get_surface()
        except (AttributeError, TypeError, pygame.error):   # older pygame: plain window
            self.window = None
            self.screen = pygame.display.set_mode(WINDOW_SIZE)
            pygame.display.set_caption("Chess using Minimax with Alpha-Beta Pruning")
        self.width, self.height = WINDOW_SIZE                # logical size, used for layout
        self.scale = self.screen.get_width() / WINDOW_SIZE[0]

        self.font_title = self._font(24)
        self.font_big = self._font(44)
        self.font = self._font(16, bold=False)
        self.font_bold = self._font(16)
        self.font_small = self._font(12)

        self.theme_index = 0
        self.images = self._load_images()
        self.choice_images = self._load_choice_images()
        self._backgrounds = {}

    def flip(self):
        """Show the finished frame."""
        if self.window is not None:
            self.window.flip()
        else:
            pygame.display.flip()

    # ------------------------------------------------------------ themes
    @property
    def theme(self):
        return THEMES[self.theme_index]

    def next_theme(self):
        self.theme_index = (self.theme_index + 1) % len(THEMES)

    # ------------------------------------------------------ logical -> physical
    def _s(self, value):
        return round(value * self.scale)

    def _pos(self, pos):
        return self._s(pos[0]), self._s(pos[1])

    def _rect(self, rect):
        rect = pygame.Rect(rect)
        return pygame.Rect(self._s(rect.x), self._s(rect.y), self._s(rect.w), self._s(rect.h))

    # ------------------------------------------------------------ assets
    def _font(self, size, bold=True):
        cache = self.__dict__.setdefault("_font_cache", {})
        if (size, bold) not in cache:
            cache[(size, bold)] = Font(size, bold, self.scale)
        return cache[(size, bold)]

    #Pieces drawn from python-chess's vector (SVG) set at full resolution, so they stay sharp.
    #Falls back to the PNGs in frontend/images (then to lettered disks) if SVG loading fails.
    def _load_images(self):
        images, size = {}, self._s(SQUARE)
        for piece_type, symbol in PIECE_SYMBOLS.items():
            for color, letter in ((chess.WHITE, "w"), (chess.BLACK, "b")):
                try:
                    svg = chess.svg.piece(chess.Piece(piece_type, color))
                    images[(piece_type, color)] = pygame.image.load_sized_svg(
                        io.BytesIO(svg.encode()), (size, size)).convert_alpha()
                    continue
                except (AttributeError, pygame.error):
                    pass
                try:
                    image = pygame.image.load(os.path.join(IMAGES_DIR, f"{letter}{symbol}.png")).convert_alpha()
                    images[(piece_type, color)] = pygame.transform.smoothscale(image, (size, size))
                except (pygame.error, FileNotFoundError):
                    images[(piece_type, color)] = self._fallback_piece(symbol, color)
        return images

    #Allows a lettered disk to be used when the image for piece is missing or fails to load
    def _fallback_piece(self, symbol, color):
        size = self._s(SQUARE)
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        fill, ink = ((250, 250, 250), (20, 20, 20)) if color == chess.WHITE else ((40, 40, 40), (240, 240, 240))
        center = (size // 2, size // 2)
        pygame.draw.circle(surface, fill, center, size // 2 - self._s(8))
        pygame.draw.circle(surface, ink, center, size // 2 - self._s(8), self._s(2))
        label = self.font_title.render(symbol, True, ink)
        surface.blit(label, label.get_rect(center=center))
        return surface

    #Load the white / random / black selection tiles from the images folder.
    def _load_choice_images(self):
        images, size = {}, self._s(TILE_SIZE)
        for key, name in CHOICE_NAMES.items():
            path = os.path.join(IMAGES_DIR, f"{name}.png")
            try:
                image = pygame.image.load(path).convert_alpha()
                images[key] = pygame.transform.smoothscale(image, (size, size))
            except (pygame.error, FileNotFoundError):
                images[key] = self._fallback_choice(key)
        return images

    def _fallback_choice(self, key):
        size = self._s(TILE_SIZE)
        surface = pygame.Surface((size, size))
        fill, ink, symbol = {"white": ((20, 20, 20), (240, 240, 240), "W"),
                             "black": ((240, 240, 240), (20, 20, 20), "B"),
                             "random": ((240, 240, 240), (20, 20, 20), "?")}[key]
        surface.fill(fill)
        label = self.font_title.render(symbol, True, ink)
        surface.blit(label, label.get_rect(center=(size // 2, size // 2)))
        return surface

    #Board squares in the current theme's colours (cached per theme; orientation doesn't
    #change the pattern because a1 and h8 are both dark).
    def _background(self):
        key = self.theme_index
        if key not in self._backgrounds:
            size = self._s(BOARD_SIZE)
            surface = pygame.Surface((size, size))
            surface.fill(self.theme["light"])
            for row in range(8):
                for col in range(8):
                    if (row + col) % 2 == 1:
                        pygame.draw.rect(surface, self.theme["dark"], self._rect((col * SQUARE, row * SQUARE, SQUARE, SQUARE)))
            self._backgrounds[key] = surface
        return self._backgrounds[key]

    # ------------------------------------------------------- coordinates (logical)

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
        rect = image.get_rect(center=self._pos(pos)) if center else image.get_rect(topleft=self._pos(pos))
        self.screen.blit(image, rect)

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
        self.screen.blit(image, image.get_rect(**{anchor: self._pos(pos)}))

    def draw_panel_background(self, title="Chess Agents", subtitle=""):
        pygame.draw.rect(self.screen, PANEL, self._rect((BOARD_SIZE, 0, PANEL_WIDTH, BOARD_SIZE)))
        self.text_at(title, self.fit_font(title, 24, PANEL_INNER), TEXT, (PANEL_CENTRE_X, 24))
        if subtitle:
            self.text_at(subtitle, self.fit_font(subtitle, 16, PANEL_INNER, bold=False), MUTED,
                         (PANEL_CENTRE_X, 50))

    def _tint(self, square, color, flipped):
        size = self._s(SQUARE)
        overlay = pygame.Surface((size, size), pygame.SRCALPHA)
        overlay.fill(color)
        self.screen.blit(overlay, self._pos(self.square_to_xy(square, flipped)))

    def draw_board(self, shown, flipped, last_move=None, selected=None, targets=(),
                   drag_square=None, mouse_pos=(0, 0), promo_color=None):

        theme = self.theme
        self.screen.blit(self._background(), (0, 0))

        if last_move:                                   # last move: theme-coloured from/to squares
            self._tint(last_move.from_square, theme["last"], flipped)
            self._tint(last_move.to_square, theme["last"], flipped)
        if shown.is_check():
            self._tint(shown.king(shown.turn), CHECK_HL, flipped)
        if selected is not None:
            self._tint(selected, SELECTED_HL, flipped)

        for square in chess.SQUARES:                    # rank / file labels
            x, y = self.square_to_xy(square, flipped)
            on_light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            ink = theme["dark"] if on_light else theme["light"]
            if x == 0:
                self.text(str(chess.square_rank(square) + 1), self.font_small, ink, (x + 3, y + 2))
            if y == BOARD_SIZE - SQUARE:
                self.text(chess.FILE_NAMES[chess.square_file(square)], self.font_small, ink,
                          (x + SQUARE - 11, y + SQUARE - 16))

        for square, piece in shown.piece_map().items():
            if square == drag_square:
                continue
            self.screen.blit(self.images[(piece.piece_type, piece.color)], self._pos(self.square_to_xy(square, flipped)))

        if selected is not None:                        # legal-move hints, drawn over pieces
            hints = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            for square, is_capture in targets:
                x, y = self.square_to_xy(square, flipped)
                centre = self._pos((x + SQUARE // 2, y + SQUARE // 2))
                if is_capture:
                    pygame.draw.circle(hints, HINT, centre, self._s(SQUARE // 2 - 2), self._s(6))
                else:
                    pygame.draw.circle(hints, HINT, centre, self._s(12))
            self.screen.blit(hints, (0, 0))

        if drag_square is not None:
            piece = shown.piece_at(drag_square)
            if piece:
                image = self.images[(piece.piece_type, piece.color)]
                self.screen.blit(image, image.get_rect(center=self._pos(mouse_pos)))

        if promo_color is not None:
            size = self._s(BOARD_SIZE)
            shade = pygame.Surface((size, size), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            self.screen.blit(shade, (0, 0))
            for piece_type, rect in self.promotion_rects():
                hovered = rect.collidepoint(mouse_pos)
                pygame.draw.rect(self.screen, (230, 230, 230) if hovered else (190, 190, 190),
                                 self._rect(rect), border_radius=self._s(8))
                self.screen.blit(self.images[(piece_type, promo_color)], self._rect(rect))

    def draw_buttons(self, buttons, mouse_pos):
        for button in buttons:
            enabled = button.is_enabled()
            hovered = enabled and button.rect.collidepoint(mouse_pos)
            if not enabled:
                fill, ink = BUTTON_DISABLED, DISABLED_TEXT
            else:
                normal, hover = button.color or (BUTTON, BUTTON_HOVER)
                fill, ink = (hover if hovered else normal), TEXT
            pygame.draw.rect(self.screen, fill, self._rect(button.rect), border_radius=self._s(6))
            self.text(button.text(), self.font_bold, ink, button.rect.center, center=True)

    #Colour-choice tiles: the selected one is bright with a green border, the rest are dimmed.
    def draw_tiles(self, tiles, selected_key, mouse_pos):
        for tile in tiles:
            rect = self._rect(tile.rect)
            self.screen.blit(self.choice_images[tile.key], rect)
            if tile.key != selected_key:
                dim = pygame.Surface(rect.size, pygame.SRCALPHA)
                dim.fill((0, 0, 0, 50 if tile.rect.collidepoint(mouse_pos) else 130))
                self.screen.blit(dim, rect)
            border = rect.inflate(self._s(6), self._s(6))
            if tile.key == selected_key:
                pygame.draw.rect(self.screen, ACCENT, border, width=self._s(3), border_radius=self._s(4))
            else:
                pygame.draw.rect(self.screen, BUTTON, border, width=max(1, self._s(1)), border_radius=self._s(4))
            caption = {"white": "White", "random": "Random", "black": "Black"}[tile.key]
            self.text(caption, self.font_small, TEXT if tile.key == selected_key else MUTED,
                      (tile.rect.centerx, tile.rect.bottom + 12), center=True)

    ##   Status box. right_text: e.g. the Stockfish evaluation "+0.42".
    def draw_status(self, headline, detail, thinking, think_phase, top=284, right_text=None):
        box = pygame.Rect(PANEL_X, top, PANEL_INNER, 62)
        pygame.draw.rect(self.screen, BACKGROUND, self._rect(box), border_radius=self._s(6))
        self.text(headline, self.font_bold, ACCENT if thinking else TEXT, (box.x + 10, box.y + 8))
        self.text(detail, self.font, MUTED, (box.x + 10, box.y + 30))
        if right_text:
            self.text_at(right_text, self.font_bold, TEXT, (box.right - 10, box.y + 8), "topright")

    #Stockfish evaluation bar in the gap between the board and the panel.
    #white_share: 0..1 fraction of the bar that is white (None = not evaluated yet).
    def draw_eval_bar(self, white_share, flipped):
        bar = pygame.Rect(BOARD_SIZE + 2, 0, EVAL_BAR_WIDTH, BOARD_SIZE)
        pygame.draw.rect(self.screen, EVAL_BLACK, self._rect(bar))
        share = 0.5 if white_share is None else white_share
        white_h = bar.h * share
        white_y = bar.y if flipped else bar.bottom - white_h   # White's side is nearest White's pieces
        pygame.draw.rect(self.screen, EVAL_WHITE, self._rect((bar.x, white_y, bar.w, white_h)))
        pygame.draw.line(self.screen, MUTED, self._pos((bar.x, bar.centery)), self._pos((bar.right - 1, bar.centery)),
                         max(1, self._s(1)))
        pygame.draw.rect(self.screen, BUTTON_HOVER, self._rect(bar), width=max(1, self._s(1)))

    @staticmethod
    def move_list_area():
        return pygame.Rect(PANEL_X, MOVES_TOP + 22, PANEL_INNER, MOVES_BOTTOM - MOVES_TOP - 22)

    @classmethod
    def visible_rows(cls):
        return max(1, (cls.move_list_area().h - 8) // MOVE_ROW_HEIGHT)

    #Two-column move list; the displayed move is highlighted in the theme's last-move colour.
    def draw_move_list(self, san_moves, shown_ply, start_row):
        self.text("Moves", self.font_bold, MUTED, (PANEL_X, MOVES_TOP))
        area = self.move_list_area()
        pygame.draw.rect(self.screen, BACKGROUND, self._rect(area), border_radius=self._s(6))
        highlight = self.theme["last"][:3]
        visible = self.visible_rows()
        rows = (len(san_moves) + 1) // 2
        for row in range(start_row, min(rows, start_row + visible)):
            y = area.y + 6 + (row - start_row) * MOVE_ROW_HEIGHT
            self.text(f"{row + 1}.", self.font, MUTED, (area.x + 8, y))
            for column in (0, 1):
                ply = row * 2 + column
                if ply < len(san_moves):
                    x = area.x + 50 + column * 130
                    current = ply + 1 == shown_ply
                    if current:
                        pygame.draw.rect(self.screen, highlight, self._rect((x - 4, y - 2, 90, MOVE_ROW_HEIGHT - 1)),
                                         border_radius=self._s(4))
                    self.text(san_moves[ply], self.font_bold, EVAL_BLACK if current else TEXT, (x, y))
        if rows > visible:                              # scroll bar
            track = pygame.Rect(area.right - 8, area.y + 4, 4, area.h - 8)
            pygame.draw.rect(self.screen, BUTTON, self._rect(track), border_radius=self._s(2))
            thumb_h = max(20, int(track.h * visible / rows))
            thumb_y = track.y + int((track.h - thumb_h) * start_row / (rows - visible))
            pygame.draw.rect(self.screen, MUTED, self._rect((track.x, thumb_y, track.w, thumb_h)),
                             border_radius=self._s(2))
