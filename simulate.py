"""
simulate.py

Tests the core resource-cost claim:

  "The attacker perceives an exponentially branching space, but we only
   ever pay compute for the rooms they actually step into."

We simulate an attacker as an agent doing a randomized depth-biased walk
through the tree (some probability of pushing deeper vs backtracking vs
trying a sibling), starting at the root. Each time the attacker steps
into a node we have not yet built, we lazily expand it (this is the only
point at which we pay any cost). We track:

  - materialized_nodes: how many rooms we actually had to build (real cost)
  - theoretical_nodes_at_max_depth_reached: how big the FULL tree would be
    if we had eagerly built everything up to the deepest point the
    attacker reached (the naive alternative, and also a proxy for how
    "big" the maze feels to the attacker)
  - steps_taken: how long the attacker spent before giving up / getting caught

This directly tests whether the hyperbolic/lazy approach is a real win or
just an elegant-but-pointless idea.
"""

import random
import numpy as np
import hyperbolic_maze as hm


def simulate_attacker(branching=4, edge_length=1.1, max_steps=500,
                       push_deeper_prob=0.55, detection_prob_per_step=0.01,
                       seed=None):
    rng = random.Random(seed)

    root = hm.make_root()
    materialized = {root.id: root}
    next_id = [1]  # mutable counter

    def ensure_expanded(node):
        if not node.children:
            children, nid = hm.expand_node(node, branching, edge_length, next_id[0])
            next_id[0] = nid
            for c in children:
                materialized[c.id] = c
        return node.children

    current = root
    max_depth_reached = 0
    path_length = 0
    caught = False

    for step in range(max_steps):
        # detection check ("measurement collapses the state")
        if rng.random() < detection_prob_per_step:
            caught = True
            break

        children = ensure_expanded(current)
        # decide: push deeper (pick a child) or backtrack (go to parent)
        can_backtrack = current.parent is not None
        if children and (rng.random() < push_deeper_prob or not can_backtrack):
            current = rng.choice(children)
            path_length += 1
        elif can_backtrack:
            current = current.parent
            path_length += 1
        else:
            # stuck at root with push_deeper failing and nowhere to backtrack
            current = rng.choice(children) if children else current

        max_depth_reached = max(max_depth_reached, current.depth)

    theoretical_full_size = sum(
        branching * (branching - 1) ** (d - 1) if d > 0 else 1
        for d in range(max_depth_reached + 1)
    )

    return {
        "materialized_nodes": len(materialized),
        "theoretical_full_tree_at_reached_depth": theoretical_full_size,
        "max_depth_reached": max_depth_reached,
        "steps_taken": step + 1,
        "caught": caught,
        "savings_factor": theoretical_full_size / max(1, len(materialized)),
    }


def run_batch(n_runs=200, **kwargs):
    results = [simulate_attacker(seed=i, **kwargs) for i in range(n_runs)]
    avg = lambda key: sum(r[key] for r in results) / len(results)
    caught_rate = sum(1 for r in results if r["caught"]) / len(results)
    print(f"Runs: {n_runs}")
    print(f"  Avg materialized (real cost) nodes : {avg('materialized_nodes'):.1f}")
    print(f"  Avg 'full tree' size at reached depth: {avg('theoretical_full_tree_at_reached_depth'):.1f}")
    print(f"  Avg savings factor (full/real)      : {avg('savings_factor'):.1f}x")
    print(f"  Avg max depth reached               : {avg('max_depth_reached'):.2f}")
    print(f"  Avg steps before stop               : {avg('steps_taken'):.1f}")
    print(f"  Fraction caught by detection         : {caught_rate:.2%}")
    return results


if __name__ == "__main__":
    print("=== Branching=4, moderate detection ===")
    run_batch(n_runs=300, branching=4, max_steps=500, detection_prob_per_step=0.01)

    print()
    print("=== Branching=6, low detection (harder maze, patient attacker) ===")
    run_batch(n_runs=300, branching=6, max_steps=1000, detection_prob_per_step=0.005)

    print()
    print("=== Branching=3, high detection (fast trip-wire) ===")
    run_batch(n_runs=300, branching=3, max_steps=300, detection_prob_per_step=0.03)
