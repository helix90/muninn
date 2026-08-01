"""
Auto-layout for the pipeline editor canvas.

Assigns grid positions to agents using a layered (left-to-right) layout
based on topological sort of their AgentLink connections.
"""

from collections import defaultdict, deque
from typing import Dict, List


NODE_W = 220
NODE_H = 80
H_GAP = 100   # horizontal gap between layers
V_GAP = 50    # vertical gap between nodes in the same layer
CANVAS_MARGIN_X = 80
CANVAS_CENTER_Y = 400


def compute_layout(agents, links) -> Dict[int, Dict[str, int]]:
    """
    Compute canvas positions for a set of agents connected by links.

    Args:
        agents: list of Job model objects
        links:  list of AgentLink model objects

    Returns:
        Dict mapping agent.id → {"x": int, "y": int}
    """
    if not agents:
        return {}

    agent_ids = {a.id for a in agents}

    # Build adjacency and in-degree within this agent set
    out_edges: Dict[int, List[int]] = {a.id: [] for a in agents}
    in_degree: Dict[int, int] = {a.id: 0 for a in agents}

    for link in links:
        src = link.source_agent_id
        tgt = link.target_agent_id
        if src in agent_ids and tgt in agent_ids:
            out_edges[src].append(tgt)
            in_degree[tgt] += 1

    # BFS from zero-in-degree nodes, tracking longest path to each node (layer)
    layer_of: Dict[int, int] = {}
    queue = deque()
    for aid in agent_ids:
        if in_degree[aid] == 0:
            layer_of[aid] = 0
            queue.append(aid)

    visited = set()
    while queue:
        aid = queue.popleft()
        if aid in visited:
            continue
        visited.add(aid)
        for neighbor in out_edges[aid]:
            new_layer = layer_of[aid] + 1
            if neighbor not in layer_of or layer_of[neighbor] < new_layer:
                layer_of[neighbor] = new_layer
            queue.append(neighbor)

    # Disconnected agents fall back to layer 0
    for a in agents:
        if a.id not in layer_of:
            layer_of[a.id] = 0

    # Group by layer, sort by id for stable output
    by_layer: Dict[int, List[int]] = defaultdict(list)
    for aid, layer in layer_of.items():
        by_layer[layer].append(aid)
    for layer in by_layer:
        by_layer[layer].sort()

    # Assign pixel positions
    positions: Dict[int, Dict[str, int]] = {}
    for layer, ids in sorted(by_layer.items()):
        x = CANVAS_MARGIN_X + layer * (NODE_W + H_GAP)
        total_h = len(ids) * NODE_H + (len(ids) - 1) * V_GAP
        y_start = max(CANVAS_MARGIN_X, CANVAS_CENTER_Y - total_h // 2)
        for i, aid in enumerate(ids):
            positions[aid] = {
                "x": x,
                "y": y_start + i * (NODE_H + V_GAP),
            }

    return positions
