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

from board_view import (BACKGROUND, BOARD_SIZE, MUTED, PANEL_INNER, PANEL_X, TEXT, Button, BoardView)
from backend.agents import agent_a, agent_d

MIN_DEPTH, MAX_DEPTH, DEFAULT_DEPTH = 1, 4, 3

# (module, class) for each agent. Index 0 = defensive, 1 = aggressive.
AGENT_MODULES = [("agent_d", "DefensiveAgent"),
               ("agent_a", "AggressiveAgent")]

AGENT_NAMES = [cls.replace("Agent", "") for _, cls in AGENT_MODULES]


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
    except (ImportError, AttributeError) as exc:
        print(f"Could not load {class_name}: {exc}")
        return PlaceholderAgent(class_name.replace("Agent", ""))

def get_depth(agent):
    return getattr(agent, "depth", DEFAULT_DEPTH)


def set_depth(agent, depth):
    agent.depth = max(MIN_DEPTH, min(MAX_DEPTH, depth))


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

        self.selected = None            # human UI state
        self.dragging = False
        self.promotion_move = None      # (from, to) while the picker is open

        self.thinking = False
        self.thinking_agent = None
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
        return self.outcome() is not None

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

    # ------------------------------------------------------------------- moves
    
    #Play a legal move and record it in the move list.
    def push_move(self, move):
        self.san_moves.append(self.board.san(move))
        self.board.push(move)
        self.selected, self.promotion_move, self.view_ply, self.status_message = None, None, None, ""

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

    def click_board(self, square):
        """Pick up a piece, or move the selected piece onto ``square``."""
        if square is None:
            return
        if self.selected is not None and square != self.selected and self.try_human_move(self.selected, square):
            return
        piece = self.board.piece_at(square)
        if piece and piece.color == self.board.turn:
            self.selected, self.dragging = square, True
        else:
            self.selected = None

    def release(self, square):
        """Mouse released: drop a dragged piece onto ``square``."""
        self.dragging = False
        if square is not None and self.selected is not None and square != self.selected:
            self.try_human_move(self.selected, square)

    def choose_promotion(self, piece_type):
        from_square, to_square = self.promotion_move
        self.push_move(chess.Move(from_square, to_square, promotion=piece_type))

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

        threading.Thread(target=work, daemon=True).start()


    def abort_search(self):
        """Cancel the running search and switch Auto off."""
        self._stop_agent()
        self.token += 1
        self.thinking, self.auto, self.step_requested = False, False, False
        self.status_message = "Aborted - press Auto or Step to continue"

    def _stop_agent(self):
        if self.thinking and self.thinking_agent is not None:
            self.thinking_agent.abort()

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

    def navigate(self, delta):
        """Review history: -1 back one ply, +1 forward (returns to live at the end)."""
        new_ply = max(0, min(len(self.san_moves), self.shown_ply() + delta))
        self.view_ply = None if new_ply == len(self.san_moves) else new_ply
        self.selected, self.promotion_move, self.dragging = None, None, False

    def status_lines(self):
        """(headline, detail) for the status box."""
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
            return "Your move", f"{side} to move"
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
        self.human_white = True
        self.depths = [DEFAULT_DEPTH, DEFAULT_DEPTH]
        self.white_agent = 0            # agent-vs-agent: which agent plays White
        self.mode = "hva"
        self.opponent = 0

        self.menu_x = (self.view.screen.get_width() - 380) // 2
        self.menu_buttons = self._build_menu_buttons()
        self.game_buttons = []

    # -------------------------------------------------------------- navigation
    
    #Create fresh agents and a new Game, then switch to the game screen.
    def start_game(self, mode, opponent=0):
        if self.game:
            self.game.close()
        self.mode, self.opponent = mode, opponent
        self.agents = [load_agent(0), load_agent(1)]
        for agent, depth in zip(self.agents, self.depths):
            set_depth(agent, depth)

        if mode == "hva":
            human = chess.WHITE if self.human_white else chess.BLACK
            seats = {human: None, not human: self.agents[opponent]}
            self.game = Game(seats, flipped=not self.human_white)
        else:
            w = self.white_agent
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
    def _build_menu_buttons(self):
        x = self.menu_x

        def toggle_colour():
            self.human_white = not self.human_white

        def swap_white():
            self.white_agent = 1 - self.white_agent

        def depth(i, d):
            self.depths[i] = max(MIN_DEPTH, min(MAX_DEPTH, self.depths[i] + d))

        buttons = [
            Button((x, 150, 380, 38), f"Play vs {AGENT_NAMES[0]} agent", lambda: self.start_game("hva", 0)),
            Button((x, 196, 380, 38), f"Play vs {AGENT_NAMES[1]} agent", lambda: self.start_game("hva", 1)),
            Button((x, 242, 380, 34), lambda: "You play: " + ("White" if self.human_white else "Black"),
                   toggle_colour),
            Button((x, 296, 380, 38), "Agent vs Agent", lambda: self.start_game("ava")),
            Button((x, 342, 380, 34), lambda: f"White: {AGENT_NAMES[self.white_agent]}  (click to swap)", swap_white),
        ]
        for i in (0, 1):
            y = 400 + i * 36
            buttons.append(Button((x + 250, y, 30, 28), "-", lambda i=i: depth(i, -1)))
            buttons.append(Button((x + 350, y, 30, 28), "+", lambda i=i: depth(i, +1)))
        buttons.append(Button((x, 480, 380, 34), "Quit", self.quit))
        return buttons

    def _build_game_buttons(self):
        g = self.game
        full, half = PANEL_INNER, (PANEL_INNER - 8) // 2
        third = (PANEL_INNER - 12) // 3
        x2, x3 = PANEL_X + third + 6, PANEL_X + 2 * (third + 6)

        def change_depth(i, d):
            set_depth(self.agents[i], get_depth(self.agents[i]) + d)

        buttons = [
            Button((PANEL_X, 44, half, 34), "Menu", self.go_to_menu),
            Button((PANEL_X + half + 8, 44, half, 34), "Restart", self.restart),
        ]
        for i in (0, 1):
            y = 128 + i * 34
            buttons.append(Button((PANEL_X + full - 110, y, 30, 26), "-", lambda i=i: change_depth(i, -1)))
            buttons.append(Button((PANEL_X + full - 30, y, 30, 26), "+", lambda i=i: change_depth(i, +1)))
        buttons += [
            Button((PANEL_X, 202, third, 32), "Abort", g.abort_search),
            Button((x2, 202, third, 32), lambda: "Auto: ON" if g.auto else "Auto: OFF", g.toggle_auto),
            Button((x3, 202, third, 32), "Step", g.step_once),
            Button((PANEL_X, 242, half, 32), "<", lambda: g.navigate(-1)),
            Button((PANEL_X + half + 8, 242, half, 32), ">", lambda: g.navigate(+1)),
        ]
        return buttons

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
            if button.rect.collidepoint(pos):
                button.action()
                return 

    def _menu_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click_buttons(self.menu_buttons, event.pos)
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
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[0] >= BOARD_SIZE:
                self._click_buttons(self.game_buttons, event.pos)      # may leave the game
            elif g.promotion_move:
                for piece_type, rect in self.view.promotion_rects():
                    if rect.collidepoint(event.pos):
                        g.choose_promotion(piece_type)
                        return
                g.promotion_move = None                                # click elsewhere cancels
            elif g.can_human_move():
                g.click_board(self.view.xy_to_square(event.pos, g.flipped))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and g.dragging:
            g.release(self.view.xy_to_square(event.pos, g.flipped))

    # ----------------------------------------------------------------- drawing
    def draw_menu(self):
        v, x = self.view, self.menu_x
        mid = v.screen.get_width()
        v.text("COMP3220 Chess AI", v.font_big, TEXT, (mid // 2, 70), center=True)
        v.text("Minmax with Alpha-Beta Pruning", v.font, MUTED, (mid // 2, 112), center=True)

        v.text("Search depth: ", v.font_bold, MUTED, (x, 372 + 0))
        v.draw_buttons(self.menu_buttons, self.mouse_pos)
        for i in (0, 1):
            y = 396 + i * 38
            v.text(f"{AGENT_NAMES[i]} agent", v.font, TEXT, (x, y + 4))
            v.text(str(self.depths[i]), v.font_bold, TEXT, (x + 315, y + 14), center=True)

    def draw_game(self):
        v, g = self.view, self.game
        shown = g.shown_board()
        live = g.view_ply is None
        promo = g.board.turn if g.promotion_move else None
        v.draw_board(g.shown_board(), g.flipped, g.last_move(),
                     g.selected if live else None,
                     g.targets() if live else (),
                     g.selected if (g.dragging and live) else None,
                     self.mouse_pos, g.board.turn if g.promotion_move else None)

        v.draw_panel_background()
        v.draw_buttons(self.game_buttons, self.mouse_pos)
        for i, agent in enumerate(self.agents):
            y = 128 + i * 34
            v.text(f"{agent.name} depth", v.font, MUTED, (PANEL_X, y + 3))
            v.text(str(get_depth(agent)), v.font_bold, TEXT, (PANEL_X + PANEL_INNER - 55, y + 13), center=True)
        headline, detail = g.status_lines()
        #v.draw_status(headline, detail, g.thinking, time.time() * 1.2)
        v.draw_move_list(g.san_moves, g.shown_ply())

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
