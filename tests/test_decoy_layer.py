import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decoy_layer import SuperpositionGroup
from scipy.stats import ks_2samp


def test_group_has_exactly_one_real_session():
    group = SuperpositionGroup(n_decoys=4, seed=1)
    real_sessions = [s for s in group.sessions if s.is_real]
    assert len(real_sessions) == 1


def test_group_size_is_decoys_plus_one():
    group = SuperpositionGroup(n_decoys=6, seed=1)
    assert len(group.sessions) == 7


def test_anomaly_on_real_session_triggers_migration_not_capture():
    group = SuperpositionGroup(n_decoys=3, seed=2, detection_threshold=3.0)
    real_id = group.real_session.id
    old_backend = group.real_session.backend_id
    group.apply_anomaly_event(real_id, 5.0)
    assert group.real_session.migrated is True
    assert group.real_session.caught is False
    assert group.real_session.backend_id != old_backend


def test_anomaly_on_decoy_session_marks_it_caught_not_migrated():
    group = SuperpositionGroup(n_decoys=3, seed=3, detection_threshold=3.0)
    decoy = [s for s in group.sessions if not s.is_real][0]
    group.apply_anomaly_event(decoy.id, 5.0)
    assert decoy.caught is True
    assert decoy.migrated is False


def test_migration_is_invisible_to_group_size():
    """After a real-session migration, the group should still look the same
    shape from the outside (same number of sessions) -- the point of the
    migration is that nothing about the group's visible structure changes."""
    group = SuperpositionGroup(n_decoys=4, seed=4, detection_threshold=3.0)
    before = len(group.sessions)
    group.apply_anomaly_event(group.real_session.id, 5.0)
    after = len(group.sessions)
    assert before == after


def test_below_threshold_anomaly_does_not_trigger_collapse():
    group = SuperpositionGroup(n_decoys=3, seed=5, detection_threshold=10.0)
    group.apply_anomaly_event(group.real_session.id, 1.0)
    assert group.real_session.migrated is False


def test_decoy_timing_distribution_matches_real_session_by_default():
    """Direct KS-test spot check: same params should draw from the same
    distribution family (sanity check underlying test_indistinguishability.py's
    Monte Carlo version)."""
    group = SuperpositionGroup(n_decoys=1, base_latency_ms=50.0, jitter_ms=5.0, seed=42)
    samples = group.observe_latencies(n_samples=1000)
    real = samples[group.real_session.id]
    decoy_id = [s.id for s in group.sessions if not s.is_real][0]
    decoy = samples[decoy_id]
    stat, p = ks_2samp(real, decoy)
    # not asserting p > 0.05 here (single draw is noisy by nature -- see
    # test_indistinguishability.py for the proper Monte Carlo version) --
    # just confirming the KS statistic itself is small, i.e. distributions
    # are close.
    assert stat < 0.15
