import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import hyperbolic_maze as hm


def test_all_points_stay_inside_unit_disk():
    root, nodes = hm.generate_full_tree(branching=5, max_depth=6, edge_length=1.2)
    max_r = max(abs(n.pos) for n in nodes)
    assert max_r < 1.0, f"a node escaped the Poincare disk: |pos|={max_r}"


def test_exponential_branch_counts_match_theory():
    branching = 4
    depth = 6
    root, nodes = hm.generate_full_tree(branching=branching, max_depth=depth, edge_length=1.1)
    counts = {}
    for n in nodes:
        counts[n.depth] = counts.get(n.depth, 0) + 1
    for d in range(depth + 1):
        expected = 1 if d == 0 else branching * (branching - 1) ** (d - 1)
        assert counts[d] == expected, f"depth {d}: expected {expected}, got {counts[d]}"


def test_every_non_root_node_has_exactly_one_parent_edge():
    root, nodes = hm.generate_full_tree(branching=4, max_depth=4, edge_length=1.1)
    for n in nodes:
        if n.parent is not None:
            assert n in n.parent.children


def test_rotation_matrix_is_unitary_su11():
    for theta in [0.1, 1.0, 3.0, 5.5]:
        M = hm.rot_matrix(theta)
        det_like = abs(M[0, 0]) ** 2 - abs(M[0, 1]) ** 2
        assert abs(det_like - 1.0) < 1e-9


def test_translate_matrix_is_unitary_su11():
    for r in [0.1, 0.5, 1.0, 2.0]:
        M = hm.translate_matrix(r)
        det_like = abs(M[0, 0]) ** 2 - abs(M[0, 1]) ** 2
        assert abs(det_like - 1.0) < 1e-9


def test_translate_matrix_sends_origin_to_expected_point():
    r = 1.3
    M = hm.translate_matrix(r)
    z = hm.apply(M, 0 + 0j)
    expected = np.tanh(r / 2)
    assert abs(z - expected) < 1e-9


def test_hyperbolic_distance_is_symmetric_and_nonnegative():
    z1, z2 = 0.3 + 0.1j, -0.2 + 0.5j
    d12 = hm.hyperbolic_distance(z1, z2)
    d21 = hm.hyperbolic_distance(z2, z1)
    assert d12 >= 0
    assert abs(d12 - d21) < 1e-9


def test_hyperbolic_distance_zero_for_identical_points():
    z = 0.4 - 0.2j
    assert hm.hyperbolic_distance(z, z) < 1e-9


def test_hyperbolic_distance_matches_edge_length_for_direct_children():
    edge_length = 1.15
    root, nodes = hm.generate_full_tree(branching=4, max_depth=1, edge_length=edge_length)
    for child in root.children:
        d = hm.hyperbolic_distance(root.pos, child.pos)
        assert abs(d - edge_length) < 1e-6


def test_lazy_expand_matches_eager_generation_positions():
    """The on-demand expand_node function used by the server/simulation must
    produce IDENTICAL geometry to the eager batch generator -- otherwise the
    live server's maze wouldn't be mathematically consistent with what we
    benchmarked."""
    branching, depth, edge_length = 4, 4, 1.1

    # Eager
    eager_root, eager_nodes = hm.generate_full_tree(branching, depth, edge_length)

    # Lazy, walking the exact same shape (always take child 0)
    lazy_root = hm.make_root()
    next_id = 1
    current = lazy_root
    lazy_positions = [current.pos]
    for _ in range(depth):
        children, next_id = hm.expand_node(current, branching, edge_length, next_id)
        current = children[0]
        lazy_positions.append(current.pos)

    eager_current = eager_root
    eager_positions = [eager_current.pos]
    for _ in range(depth):
        eager_current = eager_current.children[0]
        eager_positions.append(eager_current.pos)

    for lp, ep in zip(lazy_positions, eager_positions):
        assert abs(lp - ep) < 1e-9
