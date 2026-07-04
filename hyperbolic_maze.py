"""
hyperbolic_maze.py

Core engine for generating a regular tree embedded in the Poincare disk
model of hyperbolic space, using exact Mobius transformations (SU(1,1)).

Why this matters for the "trap the attacker" idea:
A regular tree with branching factor k grows in SIZE as k*(k-1)^(d-1) at
depth d -- exponential. You cannot embed that in flat (Euclidean) space
without either massive distortion or massive area. In hyperbolic space,
because the space itself has negative curvature, a tree of this shape
embeds with (locally) constant angles and edge lengths, no distortion.

Practically: this means we can generate a maze that "feels" locally like
an ordinary flat corridor system to whoever is inside it (each node looks
like an ordinary room with a fixed number of doors), while GLOBALLY the
number of reachable rooms explodes exponentially with distance from the
entry point. And critically -- we only ever have to materialize the rooms
the attacker actually visits. That's the resource-cost claim we're testing.
"""

import numpy as np

# ---------------------------------------------------------------------------
# Mobius transformations of the unit disk, represented as SU(1,1) matrices.
# A matrix M = [[a, b], [conj(b), conj(a)]] with |a|^2 - |b|^2 = 1 acts on
# z in the unit disk as:  M(z) = (a*z + b) / (conj(b)*z + conj(a))
# Composition of transforms = matrix multiplication (same order as function
# composition: (f o g) corresponds to M_f @ M_g).
# ---------------------------------------------------------------------------

def rot_matrix(theta):
    """Rotation by angle theta about the origin."""
    a = np.exp(1j * theta / 2)
    return np.array([[a, 0], [0, np.conj(a)]], dtype=complex)


def translate_matrix(r):
    """Hyperbolic translation by distance r along the positive real axis.
    Sends 0 -> tanh(r/2)."""
    a = np.cosh(r / 2)
    b = np.sinh(r / 2)  # real, so conj(b) = b
    return np.array([[a, b], [b, a]], dtype=complex)


def apply(M, z):
    a, b = M[0, 0], M[0, 1]
    c, d = M[1, 0], M[1, 1]
    return (a * z + b) / (c * z + d)


def mat_mul(M1, M2):
    return M1 @ M2


def hyperbolic_distance(z1, z2):
    """Exact Poincare-disk hyperbolic distance between two points."""
    num = abs(z1 - z2)
    den = abs(1 - np.conj(z1) * z2)
    x = num / den
    x = min(x, 1 - 1e-15)
    return 2 * np.arctanh(x)


# ---------------------------------------------------------------------------
# Tree generation
# ---------------------------------------------------------------------------

class Node:
    __slots__ = ("id", "depth", "transform", "parent", "children", "pos", "materialized")

    def __init__(self, id, depth, transform, parent=None):
        self.id = id
        self.depth = depth
        self.transform = transform
        self.parent = parent
        self.children = []       # filled in only if/when expanded
        self.pos = apply(transform, 0 + 0j)
        self.materialized = True  # whether this room has been "built" (resource cost)


def make_root():
    return Node(0, 0, np.eye(2, dtype=complex))


def expand_node(node, branching, edge_length, next_id):
    """Materialize the children of a single node on demand (lazy generation).
    Root gets `branching` children; every other node gets `branching - 1`
    (one direction is always the edge back to its parent), which is what
    keeps this a proper regular tree.
    Returns (new_children, next_id_after).
    """
    k = branching
    T = translate_matrix(edge_length)

    if node.parent is None:
        angles = [2 * np.pi * j / k for j in range(k)]
    else:
        angles = [np.pi + 2 * np.pi * i / k for i in range(1, k)]

    children = []
    for theta in angles:
        local = mat_mul(rot_matrix(theta), T)
        global_transform = mat_mul(node.transform, local)
        child = Node(next_id, node.depth + 1, global_transform, parent=node)
        next_id += 1
        node.children.append(child)
        children.append(child)

    return children, next_id


def generate_full_tree(branching=3, max_depth=6, edge_length=1.2):
    """Eagerly generate the WHOLE tree up to max_depth. Useful for
    visualization and for measuring true exponential size, but this is
    exactly what we do NOT want to do in a live deployment (see the lazy
    generator in simulate.py for the resource-cost simulation)."""
    root = make_root()
    nodes = [root]
    next_id = 1
    frontier = [root]
    for _ in range(max_depth):
        new_frontier = []
        for node in frontier:
            children, next_id = expand_node(node, branching, edge_length, next_id)
            nodes.extend(children)
            new_frontier.extend(children)
        frontier = new_frontier
    return root, nodes


# ---------------------------------------------------------------------------
# True hyperbolic geodesics for plotting edges (arcs orthogonal to the unit
# circle), not straight-line approximations.
# ---------------------------------------------------------------------------

def geodesic_arc_points(z1, z2, n=40):
    """Return an array of complex points tracing the hyperbolic geodesic
    (shortest path) between z1 and z2 inside the Poincare disk."""
    cross = (z1.real * z2.imag - z1.imag * z2.real)
    if abs(cross) < 1e-9:
        t = np.linspace(0, 1, n)
        return z1 + t * (z2 - z1)

    z3 = 1 / np.conj(z1)
    pts = [z1, z2, z3]
    x = [p.real for p in pts]
    y = [p.imag for p in pts]

    A = np.array([
        [x[1] - x[0], y[1] - y[0]],
        [x[2] - x[0], y[2] - y[0]],
    ])
    b = 0.5 * np.array([
        (x[1]**2 - x[0]**2) + (y[1]**2 - y[0]**2),
        (x[2]**2 - x[0]**2) + (y[2]**2 - y[0]**2),
    ])
    cx, cy = np.linalg.solve(A, b)
    R = np.hypot(x[0] - cx, y[0] - cy)
    center = cx + 1j * cy

    a1 = np.angle(z1 - center)
    a2 = np.angle(z2 - center)

    diff = (a2 - a1) % (2 * np.pi)
    if diff > np.pi:
        a2 -= 2 * np.pi

    angles = np.linspace(a1, a2, n)
    return center + R * np.exp(1j * angles)
