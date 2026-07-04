import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import moving_target as mt


def test_isometric_shift_preserves_distances_exactly():
    result = mt.run_comparison(branching=4, depth=5, seed=1)
    assert result["isometric_shift"]["mean_abs_error"] < 1e-9
    assert result["isometric_shift"]["max_abs_error"] < 1e-8


def test_naive_relabel_does_not_preserve_distances():
    result = mt.run_comparison(branching=4, depth=5, seed=1)
    # Naive relabeling shuffles identities randomly -- it should NOT
    # preserve distances (this confirms the test itself has power, i.e.
    # isn't trivially passing for everything).
    assert result["naive_relabel"]["mean_abs_error"] > 0.5


def test_isometric_shift_is_far_more_consistent_than_naive_across_seeds():
    for seed in range(5):
        result = mt.run_comparison(branching=4, depth=5, seed=seed)
        iso_err = result["isometric_shift"]["mean_abs_error"]
        naive_err = result["naive_relabel"]["mean_abs_error"]
        assert iso_err < 1e-9
        assert naive_err > iso_err * 1000
