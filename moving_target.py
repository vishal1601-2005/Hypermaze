"""
moving_target.py

Tests the "move the patch so the attacker doesn't know where they are"
idea specifically. There are two ways to implement this:

  (a) NAIVE relabeling: shuffle which physical backend serves which room
      ID / IP address. Cheap, but if the attacker has already measured
      relative distances between rooms (e.g. via RTT, or via topology
      probing), those measured relationships will no longer match after
      the shuffle -- which is itself a detectable signature that a shift
      just happened.

  (b) ISOMETRIC shift: apply an actual hyperbolic isometry (a Mobius
      transform in Aut(disk)) to every node's position simultaneously.
      Because isometries preserve hyperbolic distance exactly, EVERY
      pairwise relationship the attacker previously measured is still
      exactly true after the shift. There is no internal inconsistency
      to detect -- the only way to notice anything happened is to have
      an external absolute reference point, which the attacker (by
      construction) never had.

This module measures that difference directly.
"""

import random
import numpy as np
import hyperbolic_maze as hm


def naive_relabel_shift(nodes, rng):
    """Randomly permute which node occupies which position -- positions
    stay fixed, but identities are shuffled. This is what a naive
    'randomize the layout' defense does."""
    positions = [n.pos for n in nodes]
    shuffled = positions[:]
    rng.shuffle(shuffled)
    return {n.id: p for n, p in zip(nodes, shuffled)}


def isometric_shift(nodes, rng):
    """Apply one random hyperbolic isometry (rotation + translation) to
    every node's position simultaneously. This preserves all pairwise
    hyperbolic distances exactly."""
    theta = rng.uniform(0, 2 * np.pi)
    r = rng.uniform(0.3, 1.5)
    M = hm.mat_mul(hm.rot_matrix(theta), hm.translate_matrix(r))
    return {n.id: hm.apply(M, n.pos) for n in nodes}


def distance_consistency_error(nodes, new_positions, sample_pairs=200, seed=None):
    """Attacker's test for tampering: measure pairwise hyperbolic distance
    before and after a shift, for a sample of node pairs the attacker had
    already probed. Returns the average absolute error between the
    'remembered' distance and the 'current' distance after the shift.

    A truly consistent (undetectable) shift should give error ~ 0.
    An inconsistent shift (naive relabeling) will show large errors,
    because relabeling does not respect the metric structure at all.
    """
    rng = random.Random(seed)
    n = len(nodes)
    errors = []
    for _ in range(sample_pairs):
        i, j = rng.sample(range(n), 2)
        a, b = nodes[i], nodes[j]
        before = hm.hyperbolic_distance(a.pos, b.pos)
        after = hm.hyperbolic_distance(new_positions[a.id], new_positions[b.id])
        errors.append(abs(before - after))
    return {
        "mean_abs_error": float(np.mean(errors)),
        "max_abs_error": float(np.max(errors)),
    }


def run_comparison(branching=4, depth=6, edge_length=1.1, seed=0):
    root, nodes = hm.generate_full_tree(branching=branching, max_depth=depth, edge_length=edge_length)
    rng = random.Random(seed)

    naive_positions = naive_relabel_shift(nodes, rng)
    iso_positions = isometric_shift(nodes, rng)

    naive_result = distance_consistency_error(nodes, naive_positions, seed=seed)
    iso_result = distance_consistency_error(nodes, iso_positions, seed=seed)

    return {"naive_relabel": naive_result, "isometric_shift": iso_result}


if __name__ == "__main__":
    result = run_comparison()
    print("Naive relabeling (shuffle identities, no geometric guarantee):")
    print(f"  mean distance-consistency error: {result['naive_relabel']['mean_abs_error']:.4f}")
    print(f"  max  distance-consistency error: {result['naive_relabel']['max_abs_error']:.4f}")
    print()
    print("Isometric shift (apply Mobius transform to whole patch):")
    print(f"  mean distance-consistency error: {result['isometric_shift']['mean_abs_error']:.6f}")
    print(f"  max  distance-consistency error: {result['isometric_shift']['max_abs_error']:.6f}")
