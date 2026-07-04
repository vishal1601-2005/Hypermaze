"""
cycles.py

Adds cycles to the maze -- a real (though approximate) fix for a genuine
weakness in the plain tree structure used everywhere else in this repo: a
tree has ZERO cycles, which is itself a detectable signature. Real
networks and real buildings have redundant paths -- corridors that
reconnect, multiple routes between two points. A graph-analysis-aware
attacker who maps out reachability and notices every room has exactly one
path back to the entry point has learned something: this space is fake.

HONESTY NOTE: a mathematically exact regular hyperbolic tiling (a proper
{p,q} tessellation) has cycles built into its structure from the start,
and building one exactly requires solving the word problem for its
symmetry group -- real research-level graph theory, out of scope here.
What this module does instead is a well-defined, tested APPROXIMATION:
connect geometrically nearby nodes at the same depth with extra edges.
It achieves the practical goal (redundant paths exist, the graph is not a
pure tree) without claiming to be an exact tiling.

Because these cross-links are just additional pairs of points in the same
Poincare disk embedding, everything already proven about isometric shifts
applies to them automatically: an isometry preserves ALL pairwise
distances, tree edges and cross-links alike, with no special-casing
needed. That's verified in test_cycles.py.
"""

from collections import defaultdict
import numpy as np
import hyperbolic_maze as hm


def add_ring_cross_links(nodes, edge_length=1.1, max_distance_factor=1.6):
    """For each depth level, sort nodes by angular position around the disk
    and connect angularly-adjacent nodes (forming a ring at that depth) IF
    their hyperbolic distance is within a reasonable multiple of the
    standard tree edge length. This keeps cross-links geometrically
    consistent with the rest of the maze -- we only ever connect things
    that are actually nearby, never a "suspicious" long-range shortcut.

    Returns a list of (node_id_a, node_id_b, hyperbolic_distance) tuples.
    Root (depth 0) is skipped -- there's only one node there.
    """
    by_depth = defaultdict(list)
    for n in nodes:
        by_depth[n.depth].append(n)

    cross_links = []
    max_dist = edge_length * max_distance_factor

    for depth, group in by_depth.items():
        if depth == 0 or len(group) < 2:
            continue
        group_sorted = sorted(group, key=lambda n: np.angle(n.pos))
        for i in range(len(group_sorted)):
            a = group_sorted[i]
            b = group_sorted[(i + 1) % len(group_sorted)]
            if a.id == b.id:
                continue
            # skip if already directly connected as parent/child (avoid
            # duplicate edges when a ring wraps back onto a tree edge,
            # which can't actually happen at the same depth but checked
            # defensively)
            if b in a.children or a in b.children:
                continue
            d = hm.hyperbolic_distance(a.pos, b.pos)
            if d <= max_dist:
                cross_links.append((a.id, b.id, d))

    return cross_links


def cyclomatic_number(n_nodes, n_tree_edges, n_cross_links, n_components=1):
    """Standard graph theory measure of 'how many independent cycles does
    this graph have'. For a pure tree: edges = nodes - 1, so this is
    always exactly 0 -- the mathematical signature of 'this is a tree,
    not a realistic network'. Every cross-link we add increases this by
    (at most) 1."""
    total_edges = n_tree_edges + n_cross_links
    return total_edges - n_nodes + n_components


def summarize(branching=4, max_depth=6, edge_length=1.1, max_distance_factor=1.6):
    root, nodes = hm.generate_full_tree(branching=branching, max_depth=max_depth,
                                         edge_length=edge_length)
    n_nodes = len(nodes)
    n_tree_edges = n_nodes - 1  # true for any tree

    cross_links = add_ring_cross_links(nodes, edge_length=edge_length,
                                        max_distance_factor=max_distance_factor)
    n_cross = len(cross_links)

    tree_cyclomatic = cyclomatic_number(n_nodes, n_tree_edges, 0)
    full_cyclomatic = cyclomatic_number(n_nodes, n_tree_edges, n_cross)

    cross_link_lengths = [d for _, _, d in cross_links]
    avg_cross_len = float(np.mean(cross_link_lengths)) if cross_link_lengths else 0.0

    return {
        "n_nodes": n_nodes,
        "n_tree_edges": n_tree_edges,
        "n_cross_links": n_cross,
        "tree_cyclomatic_number": tree_cyclomatic,
        "full_cyclomatic_number": full_cyclomatic,
        "avg_cross_link_length": avg_cross_len,
        "tree_edge_length": edge_length,
    }


if __name__ == "__main__":
    result = summarize()
    print("=== Cycle structure comparison: pure tree vs. tree + cross-links ===\n")
    print(f"Nodes: {result['n_nodes']}")
    print(f"Tree edges: {result['n_tree_edges']}")
    print(f"Cross-links added: {result['n_cross_links']}")
    print()
    print(f"Pure tree cyclomatic number (independent cycles): {result['tree_cyclomatic_number']}")
    print(f"  -- ALWAYS exactly 0 for any tree, regardless of size. This is")
    print(f"     the detectable signature: no redundant paths anywhere.")
    print()
    print(f"With cross-links, cyclomatic number: {result['full_cyclomatic_number']}")
    print(f"  -- {result['full_cyclomatic_number']} independent redundant paths now exist.")
    print()
    print(f"Avg cross-link hyperbolic length: {result['avg_cross_link_length']:.4f}")
    print(f"Standard tree edge length:        {result['tree_edge_length']:.4f}")
    print(f"  -- close to the tree edge length means cross-links look like")
    print(f"     ordinary local connections, not suspicious long shortcuts.")
