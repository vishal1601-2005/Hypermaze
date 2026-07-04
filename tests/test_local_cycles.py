import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hyperbolic_maze as hm
import local_cycles as lc


class FakeNode:
    """Minimal stand-in so we can test wire_local_ring without needing
    real geometry -- it only cares about .id."""
    def __init__(self, id):
        self.id = id


def test_no_ring_for_zero_or_one_children():
    assert lc.wire_local_ring([]) == {}
    a = FakeNode("a")
    result = lc.wire_local_ring([a])
    assert result == {"a": []}


def test_two_children_get_single_mutual_link():
    a, b = FakeNode("a"), FakeNode("b")
    result = lc.wire_local_ring([a, b])
    assert result["a"] == ["b"]
    assert result["b"] == ["a"]


def test_three_children_form_a_full_ring():
    nodes = [FakeNode(i) for i in range(3)]
    result = lc.wire_local_ring(nodes)
    for i in range(3):
        neighbors = result[i]
        assert len(neighbors) == 2
        assert (i + 1) % 3 in neighbors
        assert (i - 1) % 3 in neighbors


def test_ring_link_count_matches_children_count_for_n_geq_3():
    for n in [3, 4, 5, 10]:
        nodes = [FakeNode(i) for i in range(n)]
        result = lc.wire_local_ring(nodes)
        total_link_endpoints = sum(len(v) for v in result.values())
        # each of the n ring edges contributes 2 endpoints
        assert total_link_endpoints == 2 * n


def test_ring_adds_a_cycle_only_for_three_or_more():
    assert lc.ring_adds_a_cycle(0) is False
    assert lc.ring_adds_a_cycle(1) is False
    assert lc.ring_adds_a_cycle(2) is False
    assert lc.ring_adds_a_cycle(3) is True
    assert lc.ring_adds_a_cycle(10) is True


def test_wiring_is_computable_from_a_single_expansion_only():
    """The core architectural claim: this only needs the children of ONE
    node, not any other part of the tree -- verified by literally only
    ever constructing one node's children and nothing else."""
    root, nodes = hm.generate_full_tree(branching=4, max_depth=1, edge_length=1.1)
    # root has 4 children; this is the ONLY expansion that ever happened
    assert len(nodes) == 5
    result = lc.wire_local_ring(root.children)
    assert len(result) == 4
    for child_id, neighbors in result.items():
        assert len(neighbors) == 2  # full ring among 4 children
