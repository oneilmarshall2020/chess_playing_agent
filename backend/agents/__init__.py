"""Registry of every player, so the GUI, match harness and CLI can create
them by name.

    make_player("aggressive", depth=3)
    make_player("stockfish", skill_level=0)

Partner agents are imported lazily, so a bug in one agent's file doesn't stop
the other agent (or the reference agents) from loading.
"""

import importlib

# name -> (module, class) for the two partners' Minimax agents
PARTNER_AGENTS = {
    "aggressive": ("backend.agents.agent_a", "AggressiveAgent"),
    "defensive": ("backend.agents.agent_d", "DefensiveAgent"),
}
REFERENCE_AGENTS = ("random", "greedy", "stockfish")
PLAYER_NAMES = (*PARTNER_AGENTS, *REFERENCE_AGENTS)


def make_player(name, depth=None, seed=None, **stockfish_options):
    """Create a fresh player by name.

    depth            search depth for the partner agents (ignored otherwise)
    seed             random seed for the random/greedy agents
    stockfish_options skill_level, think_time, nodes, path
    """
    key = name.lower()
    if key in PARTNER_AGENTS:
        module_name, class_name = PARTNER_AGENTS[key]
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception as error:
            raise ImportError(f"Could not load the {key} agent from {module_name}: {error}") from error
        return cls() if depth is None else cls(depth=depth)

    if key in REFERENCE_AGENTS:
        from backend.reference import make_reference
        return make_reference(key, seed=seed, **stockfish_options)

    raise ValueError(f"Unknown player {name!r}. Choose from: {', '.join(PLAYER_NAMES)}")
