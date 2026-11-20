#Game Logic: Menu, Game Loop

import importlib
import os
import queue
import random
import sys
import threading
import time
import chess
import pygame

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))      

from board_view import (BACKGROUND, BOARD_SIZE, CONTROLS_Y, MUTED, PANEL_INNER, PANEL_X, RED, RED_HOVER, TEXT, Button, BoardView, TILE_SIZE, Tile)

MIN_DEPTH, MAX_DEPTH, DEFAULT_DEPTH = 1, 4, 3

# (module, class) for each agent. Index 0 = defensive, 1 = aggressive.
AGENT_MODULES = [("agent_d", "DefensiveAgent"),
               ("agent_a", "AggressiveAgent")]

AGENT_NAMES = [cls.replace("Agent", "") for _, cls in AGENT_MODULES]
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
DRAW_ACCEPT_DEFICIT = 8

MENU_TITLE = "COMP3220 Chess AI"
MENU_SUBTITLE = "Minimax with Alpha-Beta Pruning"
MENU_PLAY_AS = "Play as"
MENU_AVA_NOTE = "Colours are random for the first game, then swap automatically"
MENU_DEPTH_LABEL = "Search depth (plies)"
PANEL_TITLE = "Chess Agents"        # title shown above the board panel during a game

MENU_WIDTH = 380                    # preferred width of the menu column (shrinks on a narrow window)
MENU_MARGIN = 16 

#----------------------------------------------------------------------------------Agents

#Stand-in used only if an agent module can't be imported (keeps the GUI testable).
class PlaceholderAgent:

    def __init__(self, name):
        self.name = name
        self.depth = 2


    def play(self, board):
        time.sleep(0.8)
        moves = list(board.legal_moves)
        return random.choice([m for m in moves if board.is_capture(m)] or moves)


    def abort(self):
        pass


#Create a FRESH instance of agent ``index`` (placeholder if import fails).
#A fresh instance per game means an aborted search from a previous game can never interfere with the new one through shared state.
def load_agent(index):
    if not 0 <= index < len(AGENT_MODULES):
        raise IndexError(f"Unknown agent index: {index}")

    module_name, class_name = AGENT_MODULES[index]
    try:
        module = importlib.import_module(f"backend.agents.{module_name}")
        agent_class = getattr(module, class_name)
        return agent_class()
    except Exception as exc:
        print(f"Could not load {class_name}: {exc}")
        return PlaceholderAgent(class_name.replace("Agent", ""))

def get_depth(agent):
    return getattr(agent, "depth", DEFAULT_DEPTH)

#Clamp and apply the search depth
def set_depth(agent, depth):
    agent.depth = max(MIN_DEPTH, min(MAX_DEPTH, depth))

#Decide whether ``agent`` accepts a draw offer in ``board`` (the human offered on their turn).
# If the agent defines ``accept_draw(board) -> bool`` that is used, so each strategy can
# decide in its own style (e.g. a defensive agent accepting more readily than an aggressive
# one). Otherwise the default is a material rule: accept only when behind by
# DRAW_ACCEPT_DEFICIT points or more.

def agent_accepts_draw(agent, board):
    
    custom = getattr(agent, "accept_draw", None)
    if callable(custom):
        try:
            return bool(custom(board.copy()))
        except Exception as error:
            print(f"[{agent.name}] accept_draw error: {error}; using default rule")
    agent_color = not board.turn                        # it is the human's turn when they offer
    balance = sum((PIECE_VALUES[p.piece_type] if p.color == agent_color else -PIECE_VALUES[p.piece_type])
                  for p in board.piece_map().values())
    return balance <= -DRAW_ACCEPT_DEFICIT

#---------------------------------------------------------------------------------Game

#State and rules for a single game. seats maps chess.WHITE / chess.BLACK to an agent, or to None for the human agent.
class Game:

    def __init__(self, seats, flipped=False):
        self.seats = seats
        self.flipped = flipped
        self.board = chess.Board()
        self.san_moves = []

        self.auto = True                # agents move on their own
        self.step_requested = False     # "Step" = let the side to move play once
        self.view_ply = None            # None = live position, else reviewing history
        self.status_message = ""
        self.scroll_row = None          # move list: None = follow the latest move, else first visible row

        self.draw_agreed = False
        self.resigned = None            # colour that resigned (None = nobody)
        self.resign_confirm_until = 0.0  # Resign needs a second click within this time
        self.last_offer_ply = -1

        self.selected = None            # human UI state
        self.dragging = False
        self.promotion_move = None      # (from, to) while the picker is open

        self.thinking = False
        self.thinking_agent = None
        self.worker = None
        self.think_start = 0.0
        self.last_think_time = None
        self.results = queue.Queue()    # finished searches arrive here
        self.token = 0                  # bumped on abort so stale results are ignored

    # ----------------------------------------------------------------- queries
    def agent_for(self, color):
        return self.seats[color]

    def outcome(self):
        return self.board.outcome(claim_draw=True)

    def is_over(self):
        return self.resigned is not None or self.draw_agreed or self.outcome() is not None

    def can_human_move(self):
        return (self.view_ply is None and not self.is_over() and not self.thinking
                and self.agent_for(self.board.turn) is None)

    #Ply means move, plies refer to moves (by both agents)
    def shown_ply(self):
        return len(self.san_moves) if self.view_ply is None else self.view_ply

    #Live board, or a replay of the first view_ply moves when reviewing.
    def shown_board(self):
        if self.view_ply is None:
            return self.board
        replay = chess.Board()
        for move in self.board.move_stack[:self.view_ply]:
            replay.push(move)
        return replay

    def last_move(self):
        ply = self.shown_ply()
        return self.board.move_stack[ply - 1] if ply > 0 else None

    def targets(self):
        if self.selected is None:
            return []
        return [(m.to_square, self.board.is_capture(m))
                for m in self.board.legal_moves if m.from_square == self.selected]

    def matchup_text(self):
        def name(color):
            agent = self.seats[color]
            return "You" if agent is None else agent.name
        return f"{name(chess.WHITE)} (White) vs {name(chess.BLACK)} (Black)"

    # ------------------------------------------------------------------- moves
    
    #Play a legal move and record it in the move list.
    def push_move(self, move):
        self.san_moves.append(self.board.san(move))
        self.board.push(move)
        self.selected, self.promotion_move, self.view_ply, self.status_message = None, None, None, ""
        self.scroll_row = None

    #Play from -> to if legal (opens the promotion picker if needed).
    def try_human_move(self, from_square, to_square):
        matches = [m for m in self.board.legal_moves
                   if m.from_square == from_square and m.to_square == to_square]
        if not matches:
            return False
        if any(m.promotion for m in matches):
            self.promotion_move = (from_square, to_square)
        else:
            self.push_move(matches[0])
        return True

    #Pick up a piece, or move the selected piece onto square.
    def click_board(self, square):
        if square is None:
            return
        if self.selected is not None and square != self.selected and self.try_human_move(self.selected, square):
            return
        piece = self.board.piece_at(square)
        if piece and piece.color == self.board.turn:
            self.selected, self.dragging = square, True
        else:
            self.selected = None

    #Mouse released: drop a dragged piece onto square.
    def release(self, square):
        self.dragging = False
        if square is not None and self.selected is not None and square != self.selected:
            self.try_human_move(self.selected, square)

    def choose_promotion(self, piece_type):
        from_square, to_square = self.promotion_move
        self.push_move(chess.Move(from_square, to_square, promotion=piece_type))

    #------------------------------------------------------------- Resignation

    #Colour the human plays, or None in agent-vs-agent games.
    def human_color(self):
        for color, agent in self.seats.items():
            if agent is None:
                return color
        return None

    def can_resign(self):
        return self.human_color() is not None and not self.is_over()

    def resign_label(self):
        return "Confirm?" if time.time() < self.resign_confirm_until else "Resign"

    #First click arms the button ("Confirm?"); a second click within 3 s resigns for the human.
    def request_resign(self):
        if not self.can_resign():
            return
        if time.time() >= self.resign_confirm_until:
            self.resign_confirm_until = time.time() + 3.0
            return
        self._stop_agent()                      # stop an agent that is still thinking
        self.token += 1
        self.thinking = False
        self.resigned = self.human_color()
        self.selected, self.dragging, self.promotion_move = None, False, None

    #------------------------------------------------------------- Draw offers

    #Human may offer a draw on their own turn, once per move.
    def can_offer_draw(self):
        return (self.can_human_move() and self.promotion_move is None and len(self.san_moves) != self.last_offer_ply)


    #Human offers a draw, the opposing agent decides whether to accept.
    def offer_draw(self):
        if not self.can_offer_draw():
            return
        agent = self.agent_for(not self.board.turn)
        self.last_offer_ply = len(self.san_moves)
        self.selected, self.dragging = None, False
        if agent_accepts_draw(agent, self.board):
            self.draw_agreed = True
            self.status_message = ""
        else:
            self.status_message = f"{agent.name} declined the draw"

    # ------------------------------------------------------------ Agent search
    
    #Run agent.play() in a worker thread so the window stays responsive.
    def start_search(self, agent):
        self.thinking, self.thinking_agent, self.think_start = True, agent, time.time()
        token, snapshot, started = self.token, self.board.copy(), self.think_start

        def work():
            try:
                move = agent.play(snapshot)
            except Exception as error:
                if type(error).__name__ != "SearchAborted":
                    print(f"[{agent.name}] error: {error}")
                move = None
            self.results.put((token, move, time.time() - started))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    #Ask current agent that is searching to give up.
    def _stop_agent(self):
        agent = self.thinking_agent
        if agent is None:
            return
        for name in ("abort", "stop"):          # engine agents use abort(); older ones stop()
            method = getattr(agent, name, None)
            if callable(method):
                method()
                return

    def close(self):
        """Stop everything (called when leaving the game screen)."""
        self._stop_agent()
        self.token += 1
        self.thinking = False

    def update(self):
        """Called every frame: collect finished searches, start new ones."""
        while not self.results.empty():
            token, move, seconds = self.results.get()
            if token == self.token and self.thinking:
                self.thinking, self.last_think_time = False, seconds
                if move is not None and move in self.board.legal_moves:
                    self.push_move(move)
                else:
                    self.auto, self.status_message = False, "Agent returned no legal move"
        if self.thinking or self.view_ply is not None or self.is_over():
            return
        if self.worker is not None and self.worker.is_alive():   # let an aborted search finish unwinding
            return
        agent = self.agent_for(self.board.turn)
        if agent and (self.auto or self.step_requested):
            self.start_search(agent)
        self.step_requested = False

    # ----------------------------------------------------------- panel actions
    def toggle_auto(self):
        self.auto = not self.auto
        self.status_message = ""

    #Allows the agent-to-move by exactly one move.
    def step_once(self):
        self.view_ply = None
        if not self.thinking and not self.is_over():
            self.step_requested = True

    #Review history: -1 back one ply, +1 forward (returns to live at the end).
    def navigate(self, delta):
        new_ply = max(0, min(len(self.san_moves), self.shown_ply() + delta))
        self.view_ply = None if new_ply == len(self.san_moves) else new_ply
        self.selected, self.promotion_move, self.dragging = None, None, False
        self.scroll_row = None

    #------------------------------------------------------------------------------- Move 1list scroll
    
    #First row of the move list to draw (follows the shown move unless the user scrolled).
    def move_list_start(self, visible):
        
        rows = (len(self.san_moves) + 1) // 2
        max_start = max(0, rows - visible)
        if self.scroll_row is not None:
            return max(0, min(max_start, self.scroll_row))
        target = max(0, (self.shown_ply() - 1) // 2)
        return max(0, min(target - visible + 1, max_start))

    #Scroll the move list by delta_rows (negative = up).
    def scroll_moves(self, delta_rows, visible):
        rows = (len(self.san_moves) + 1) // 2
        start = self.move_list_start(visible) + delta_rows
        self.scroll_row = max(0, min(max(0, rows - visible), start))

    #(headline, detail) for the status box.
    def status_lines(self):
        if self.resigned is not None:
            white_wins = self.resigned == chess.BLACK
            return ("White wins" if white_wins else "Black wins") + " - Resignation", "1-0" if white_wins else "0-1"
        if self.draw_agreed:
            return "Draw - Agreement", "1/2-1/2"
        outcome = self.outcome()
        if outcome:
            winner = "Draw" if outcome.winner is None else ("White wins" if outcome.winner else "Black wins")
            return f"{winner} - {outcome.termination.name.replace('_', ' ').title()}", outcome.result()
        if self.view_ply is not None:
            return f"Reviewing move {self.view_ply}/{len(self.san_moves)}", "Press > to return to the game"
        side = "White" if self.board.turn else "Black"
        if self.thinking:
            dots = "." * (int(time.time() * 3) % 4)
            return (f"{self.thinking_agent.name} is thinking{dots}",
                    f"{side} - depth {get_depth(self.thinking_agent)} - {time.time() - self.think_start:.1f}s")
        agent = self.agent_for(self.board.turn)
        if agent is None:
            return self.status_message or "Your move", f"{side} to move"
        detail = (f"Last move took {self.last_think_time:.1f}s" if self.last_think_time is not None
                  else f"{side} to move")
        return self.status_message or f"{agent.name} to move ({side})", detail


# --------------------------------------------------------------------------------App
class App:

    #Window, menu screen, game screen and the main loop.

    def __init__(self):
        self.view = BoardView()
        self.clock = pygame.time.Clock()
        self.mouse_pos = (0, 0)
        self.running = True

        self.screen_name = "menu"       # "menu" or "game"
        self.game = None
        self.agents = []

        # Menu choices (remembered between games)
        self.depths = [DEFAULT_DEPTH, DEFAULT_DEPTH]
        self.mode = "hva"               # "hva" = human vs agent, "ava" = agent vs agent
        self.opponent = 0               # hva: index of the agent the human plays against

        self.colour_choice = "white"    # hva: "white", "black" or "random"
        self.ava_white = None           # ava: index of the agent playing White (None = no game yet)

        self.menu_buttons = []
        self.tiles = []
        self._build_menu()
        self.game_buttons = []

    # -------------------------------------------------------------- navigation
    
    #Create fresh agents and a new Game, then switch to the game screen.
    def start_game(self, mode, opponent=0):
        """Create fresh agents and a new Game, then switch to the game screen."""
        if self.game:
            self.game.close()
        self.mode, self.opponent = mode, opponent
        self.agents = [load_agent(0), load_agent(1)]
        for agent, depth in zip(self.agents, self.depths):
            set_depth(agent, depth)

        if mode == "hva":
            human_white = {"white": True, "black": False}.get(self.colour_choice, random.random() < 0.5)
            human = chess.WHITE if human_white else chess.BLACK
            self.game = Game({human: None, not human: self.agents[opponent]}, flipped=not human_white)
        else:
            # first game: random colours; every later game: the agents swap colours
            self.ava_white = random.choice([0, 1]) if self.ava_white is None else 1 - self.ava_white
            w = self.ava_white
            self.game = Game({chess.WHITE: self.agents[w], chess.BLACK: self.agents[1 - w]})
        self.game_buttons = self._build_game_buttons()
        self.screen_name = "game"
            

    def restart(self):
        self.start_game(self.mode, self.opponent)

    def go_to_menu(self):
        if self.game:
            self.game.close()
        self.game = None
        self.screen_name = "menu"

    def quit(self):
        self.running = False

    # ----------------------------------------------------------------- buttons
    def _menu_flow(self, scale, y0):
        v = self.view
        width = v.screen.get_width()
        col_w = min(MENU_WIDTH, width - 2 * MENU_MARGIN)
        x, mid = (width - col_w) // 2, width // 2
        gap = max(3, round(8 * scale))                  # between related items
        section = max(6, round(22 * scale))             # between groups
        btn_h = max(26, round(38 * scale))
        row_h = max(22, round(28 * scale))
        buttons, tiles, texts = [], [], []
        y = y0

        def line_height(font):
            return font.size("Ag")[1]

        #Add a text line whose top edge is at the current y, then move down by its height.
        def label(text, font, color, anchor="midtop", at_x=None):
            nonlocal y
            texts.append((text, font, color, (at_x if at_x is not None else mid, y), anchor))
            y += line_height(font)

        # title + subtitle (the title font shrinks if the text is wider than the window)
        label(MENU_TITLE, v.fit_font(MENU_TITLE, 44, width - 2 * MENU_MARGIN), TEXT)
        y += gap
        label(MENU_SUBTITLE, v.fit_font(MENU_SUBTITLE, 16, width - 2 * MENU_MARGIN, bold=False), MUTED)
        y += section

        # human vs agent
        for i in (0, 1):
            buttons.append(Button((x, y, col_w, btn_h), f"Play vs {AGENT_NAMES[i]} agent",
                                    lambda i=i: self.start_game("hva", i)))
            y += btn_h + gap
        y += section - gap
        label(MENU_PLAY_AS, v.font_bold, MUTED, "topleft", at_x=x)
        y += gap + 3                                    # +3: room for the tile's selection border
        tile_gap = max(16, (col_w - 3 * TILE_SIZE) // 4)
        left = x + (col_w - (3 * TILE_SIZE + 2 * tile_gap)) // 2
        for i, key in enumerate(("white", "random", "black")):
            tiles.append(Tile((left + i * (TILE_SIZE + tile_gap), y, TILE_SIZE, TILE_SIZE), key,
                                lambda key=key: setattr(self, "colour_choice", key)))
        y += TILE_SIZE + line_height(v.font_small) + 10         # tile + its caption
        y += section

        # agent vs agent
        buttons.append(Button((x, y, col_w, btn_h), "Agent vs Agent", lambda: self.start_game("ava")))
        y += btn_h + gap
        for line in v.wrap_text(MENU_AVA_NOTE, v.font_small, col_w):   # long notes wrap instead of running off
            label(line, v.font_small, MUTED)
        y += section

        # search depth: label, value and - / + all share each row's vertical centre
        label(MENU_DEPTH_LABEL, v.font_bold, MUTED, "topleft", at_x=x)
        y += gap

    
        def change_depth(i, d):
            self.depths[i] = max(MIN_DEPTH, min(MAX_DEPTH, self.depths[i] + d))

        for i in (0, 1):
            centre_y = y + row_h // 2
            texts.append((f"{AGENT_NAMES[i]} agent", v.font, TEXT, (x, centre_y), "midleft"))
            buttons.append(Button((x + col_w - 130, y, 30, row_h), "-", lambda i=i: change_depth(i, -1)))
            texts.append((lambda i=i: str(self.depths[i]), v.font_bold, TEXT, (x + col_w - 65, centre_y), "center"))
            buttons.append(Button((x + col_w - 30, y, 30, row_h), "+", lambda i=i: change_depth(i, +1)))
            y += row_h + gap
        y += section - gap

        quit_h = max(26, round(34 * scale))
        buttons.append(Button((x, y, col_w, quit_h), "Quit", self.quit))
        y += quit_h
        return y, buttons, tiles, texts

    def _build_menu(self):
        height = self.view.screen.get_height()
        scale = 1.0
        while True:
            total, *_ = self._menu_flow(scale, 0)
            if total <= height - 2 * MENU_MARGIN or scale <= 0.2:
                break
            scale -= 0.1   # (windows shorter than roughly 430 px are too small for the full menu)
        top = max(MENU_MARGIN, (height - total) // 2)
        _, self.menu_buttons, self.tiles, self.menu_texts = self._menu_flow(scale, top)

    def draw_menu(self):
        v = self.view
        v.draw_buttons(self.menu_buttons, self.mouse_pos)
        v.draw_tiles(self.tiles, self.colour_choice, self.mouse_pos)
        for text, font, color, pos, anchor in self.menu_texts:
            v.text_at(text() if callable(text) else text, font, color, pos, anchor)

    def _build_game_buttons(self):
        g = self.game
        third = (PANEL_INNER - 12) // 3
        top = [
            Button((PANEL_X, 66, third, 32), "Menu", self.go_to_menu),
            Button((PANEL_X + third + 6, 66, third, 32), "Restart", self.restart),
            Button((PANEL_X + 2 * (third + 6), 66, third, 32), "Draw", g.offer_draw, enabled=g.can_offer_draw),
        ]
        # one line below the move list: Resign (red), Auto, Step, <, >
        specs = [(76, g.resign_label, g.request_resign, (RED, RED_HOVER), g.can_resign),
                 (84, lambda: "Auto: ON" if g.auto else "Auto: OFF", g.toggle_auto, None, None),
                 (64, "Step", g.step_once, None, None),
                 (42, "<", lambda: g.navigate(-1), None, None),
                 (42, ">", lambda: g.navigate(+1), None, None)]
        total = sum(w for w, *_ in specs) + 6 * (len(specs) - 1)
        x = PANEL_X + (PANEL_INNER - total) // 2
        controls = []
        for width, label, action, color, enabled in specs:
            controls.append(Button((x, CONTROLS_Y, width, 34), label, action, color=color, enabled=enabled))
            x += width + 6
        return top + controls
    
    # ------------------------------------------------------------------ events
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        if self.screen_name == "menu":
            self._menu_event(event)
        else:
            self._game_event(event)

    @staticmethod
    def _click_buttons(buttons, pos):
        for button in buttons:
            if button.rect.collidepoint(pos) and button.is_enabled():
                button.action()
                return

    def _menu_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click_buttons(self.menu_buttons + self.tiles, event.pos)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.quit()

    def _game_event(self, event):
        g = self.game
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                g.navigate(-1)
            elif event.key == pygame.K_RIGHT:
                g.navigate(+1)
            elif event.key == pygame.K_SPACE:
                g.step_once()
            elif event.key == pygame.K_ESCAPE:
                self.go_to_menu()
        elif event.type == pygame.MOUSEWHEEL:                       # scroll the move list
            if self.view.move_list_area().collidepoint(self.mouse_pos):
                g.scroll_moves(-event.y * 2, self.view.visible_rows())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[0] >= BOARD_SIZE:
                self._click_buttons(self.game_buttons, event.pos)   # may leave the game
            elif g.promotion_move:
                for piece_type, rect in self.view.promotion_rects():
                    if rect.collidepoint(event.pos):
                        g.choose_promotion(piece_type)
                        return
                g.promotion_move = None                             # clicking elsewhere cancels
            elif g.can_human_move():
                g.click_board(self.view.xy_to_square(event.pos, g.flipped))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and g.dragging:
            g.release(self.view.xy_to_square(event.pos, g.flipped))

    # ----------------------------------------------------------------- drawing
    def draw_game(self):
        v, g = self.view, self.game
        live = g.view_ply is None
        v.draw_board(g.shown_board(), g.flipped, g.last_move(),
                     g.selected if live else None,
                     g.targets() if live else (),
                     g.selected if (g.dragging and live) else None,
                     self.mouse_pos, 
                     g.board.turn if g.promotion_move else None)

        v.draw_panel_background(PANEL_TITLE, g.matchup_text())
        v.draw_buttons(self.game_buttons, self.mouse_pos)
        headline, detail = g.status_lines()
        v.draw_status(headline, detail, g.thinking, time.time() * 1.2, top = 108)
        v.draw_move_list(g.san_moves, g.shown_ply(), g.move_list_start(v.visible_rows()))

    # --------------------------------------------------------------- main loop
    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            if self.game:
                self.game.update()
            self.view.screen.fill(BACKGROUND)
            if self.screen_name == "menu":
                self.draw_menu()
            else:
                self.draw_game()
            pygame.display.flip()
            self.clock.tick(60)
        if self.game:
            self.game.close()
        pygame.quit()


def main():
    App().run()


if __name__ == "__main__":
    main()