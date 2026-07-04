"""
test_indistinguishability.py

Rigorous check of the decoy-cloning claim: can a passive external observer,
using only response timing, tell the real session apart from the decoys
BEFORE detection fires? We use the two-sample Kolmogorov-Smirnov test,
which is a standard statistical test for "do these two samples come from
the same distribution."

If decoys are well-built, KS test p-values comparing real-vs-decoy timing
should be large (fail to reject "same distribution") -- i.e. statistically
indistinguishable. If the decoys are poorly built (e.g. slightly different
latency profile because they hit a different code path), the KS test will
reliably catch it with a small p-value.
"""

from scipy.stats import ks_2samp
from decoy_layer import SuperpositionGroup


def test_well_built_decoys_are_indistinguishable(n_trials=200, n_decoys=5, alpha=0.05):
    """A single KS test at alpha=0.05 has a 5% false-positive rate BY
    DEFINITION -- flagging one decoy in one draw means nothing on its own.
    The real question is: across many independent trials, does the
    empirical false-positive rate match the expected ~alpha (meaning the
    decoys are truly indistinguishable, and any flags are just statistical
    noise), or is it far higher (meaning something about the decoys is
    actually detectable)?
    """
    flags = 0
    total = 0
    for trial in range(n_trials):
        group = SuperpositionGroup(n_decoys=n_decoys, base_latency_ms=42.0, jitter_ms=6.0, seed=trial)
        samples = group.observe_latencies(n_samples=300)
        real_samples = samples[group.real_session.id]
        for s in group.sessions:
            if s.is_real:
                continue
            _, p = ks_2samp(real_samples, samples[s.id])
            total += 1
            if p < alpha:
                flags += 1

    empirical_rate = flags / total
    # Allow generous slack around the theoretical alpha since this is a
    # finite-sample Monte Carlo estimate, not an exact calculation.
    assert empirical_rate < alpha * 2.5, (
        f"empirical false-positive rate {empirical_rate:.3f} is far above "
        f"the expected ~{alpha} -- decoys may be genuinely distinguishable"
    )
    return empirical_rate, alpha


def test_poorly_built_decoy_is_caught_by_the_same_test():
    """Sanity check: if a decoy's fingerprint is off, the KS test should
    actually catch it -- otherwise the test above would be meaningless."""
    group = SuperpositionGroup(n_decoys=1, base_latency_ms=42.0, jitter_ms=6.0, seed=2)
    # deliberately corrupt the one decoy's fingerprint
    decoy = [s for s in group.sessions if not s.is_real][0]
    decoy.fingerprint_mean_latency_ms = 65.0  # visibly different backend

    samples = group.observe_latencies(n_samples=500)
    real_samples = samples[group.real_session.id]
    stat, p = ks_2samp(real_samples, samples[decoy.id])
    assert p < 0.01, f"expected the mismatched decoy to be caught, got p={p}"
    return p


if __name__ == "__main__":
    rate, alpha = test_well_built_decoys_are_indistinguishable()
    print(f"Well-built decoys: empirical false-positive rate over many trials = {rate:.3f}")
    print(f"  (expected under 'truly indistinguishable' null hypothesis: ~{alpha})")
    print(f"  {'PASS -- decoys are statistically indistinguishable' if rate < alpha*2.5 else 'FAIL'}")

    p_bad = test_poorly_built_decoy_is_caught_by_the_same_test()
    print(f"\nSanity check -- deliberately mismatched decoy: p = {p_bad:.6f} (correctly caught, test has power)")
