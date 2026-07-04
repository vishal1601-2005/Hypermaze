"""
local_cycles.py

The lazy-compatible version of the cycles idea. Instead of ring-linking
nodes across different branches of the tree (which requires knowing about
every sibling subtree at a given depth -- fine for offline analysis in
cycles.py, but incompatible with on-demand/lazy generation), this module
links a node's own children TO EACH OTHER, in a small local ring.

This is fully computable at the moment a single node is expanded -- no
knowledge of any other branch is required -- so it preserves the laziness
property that gives the whole system its resource-cost advantage, while
still eliminating the "this is a pure tree, zero cycles" signature at a
local level: standing in any room, you can reach a sibling room directly
without walking back through the parent first.

The tradeoff versus cycles.py's whole-tree rings: these cycles are
smaller and more localized (one small ring per expansion event, rather
than one big ring spanning an entire depth level across all branches).
That's the honest price of staying lazy -- and it's still a real
improvement over zero cycles.
"""


def wire_local_ring(children):
    """Given a list of sibling nodes (children of the same parent,
    created in the same expansion event), return a dict mapping each
    child's id to the list of sibling ids it's now connected to via a
    local ring link.

    - 0 or 1 children: no ring possible, empty links.
    - 2 children: a single link between them (a "ring" of 2 is just an
      edge, not a cycle on its own, but it still gives a second option).
    - 3+ children: a full ring, each child linked to its two neighbors,
      closing into exactly one cycle.
    """
    n = len(children)
    links = {c.id: [] for c in children}

    if n < 2:
        return links

    if n == 2:
        a, b = children
        links[a.id].append(b.id)
        links[b.id].append(a.id)
        return links

    for i in range(n):
        a = children[i]
        b = children[(i + 1) % n]
        links[a.id].append(b.id)
        links[b.id].append(a.id)

    return links


def ring_adds_a_cycle(n_children):
    """A ring among n>=3 children adds exactly one independent cycle to
    the graph (n edges among n nodes that were previously only connected
    via their shared parent). n<3 adds zero independent cycles (0 or 1
    edges isn't enough to close a loop)."""
    return n_children >= 3
