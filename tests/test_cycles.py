import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hyperbolic_maze as hm
import cycles as cy


def test_pure_tree_has_zero_cyclomatic_number():
    for n_nodes, n_edges in [(10, 9), (100, 99), (5000, 4999)]:
        assert cy.cyclomatic_number(n_nodes, n_edges, 0) == 0


def test_cross_links_increase_cyclomatic_number():
    root, nodes = hm.generate_full_tree(branching=4, max_depth=5, edge_length=1.1)
    cross_links = cy.add_ring_cross_links(nodes, edge_length=1.1)
    assert len(cross_links) > 0, "expected at least some cross-links to be added"

    n_nodes = len(nodes)
    n_tree_edges = n_nodes - 1
    tree_cyc = cy.cyclomatic_number(n_nodes, n_tree_edges, 0)
    full_cyc = cy.cyclomatic_number(n_nodes, n_tree_edges, len(cross_links))

    assert tree_cyc == 0
    assert full_cyc > 0
    assert full_cyc == len(cross_links)  # each cross-link adds exactly one cycle


def test_cross_links_are_geometrically_local_not_shortcuts():
    """Cross-links should be comparable in length to a normal tree edge --
    if they were much longer, they'd be detectable as suspicious
    'teleport' shortcuts rather than ordinary nearby connections."""
    edge_length = 1.1
    root, nodes = hm.generate_full_tree(branching=4, max_depth=5, edge_length=edge_length)
    cross_links = cy.add_ring_cross_links(nodes, edge_length=edge_length, max_distance_factor=1.6)

    for _, _, d in cross_links:
        assert d <= edge_length * 1.6 + 1e-9


def test_cross_links_never_duplicate_a_tree_edge():
    root, nodes = hm.generate_full_tree(branching=4, max_depth=5, edge_length=1.1)
    cross_links = cy.add_ring_cross_links(nodes, edge_length=1.1)

    node_by_id = {n.id: n for n in nodes}
    tree_edges = set()
    for n in nodes:
        for c in n.children:
            tree_edges.add(frozenset((n.id, c.id)))

    for a_id, b_id, _ in cross_links:
        assert frozenset((a_id, b_id)) not in tree_edges


def test_isometric_shift_preserves_cross_link_distances_too():
    """The isometry-preservation guarantee proven for tree edges in
    test_moving_target.py must generalize automatically to cross-links,
    since an isometry preserves ALL pairwise distances -- no special
    casing needed. This is the actual point of building on real geometry
    instead of an ad hoc graph."""
    root, nodes = hm.generate_full_tree(branching=4, max_depth=5, edge_length=1.1)
    cross_links = cy.add_ring_cross_links(nodes, edge_length=1.1)
    assert len(cross_links) > 5, "need enough cross-links for a meaningful check"

    theta, r = 1.7, 0.8
    M = hm.mat_mul(hm.rot_matrix(theta), hm.translate_matrix(r))
    new_pos = {n.id: hm.apply(M, n.pos) for n in nodes}

    for a_id, b_id, d_before in cross_links:
        d_after = hm.hyperbolic_distance(new_pos[a_id], new_pos[b_id])
        assert abs(d_before - d_after) < 1e-9
