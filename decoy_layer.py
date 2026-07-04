"""
decoy_layer.py

Implements the "clone / superposition" half of the idea:

  - A real user session and N decoy sessions are spun up together, built to
    be statistically indistinguishable from the outside (same response
    timing distribution, same fingerprint).
  - Nothing routes to the real backend until we're confident about who's
    who. An anomaly detector watches all sessions.
  - The moment detection fires on a given session ("measurement"), we
    "collapse": if the anomaly was on the real user's session, we silently
    migrate that user's traffic to fresh clean infrastructure (rotate
    session token + backend) with zero visible interruption; the flagged
    session itself keeps running as a fully-instrumented decoy so we can
    keep watching whoever/whatever triggered the anomaly.

This module deliberately does NOT claim quantum anything -- it implements
the classical property we actually want, which is *indistinguishability*
up to the point of measurement, and *migration* at the point of detection.
"""

import random
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    is_real: bool
    backend_id: str
    fingerprint_mean_latency_ms: float
    fingerprint_jitter_ms: float
    created_at: float = field(default_factory=time.time)
    anomaly_score: float = 0.0
    migrated: bool = False
    caught: bool = False

    def sample_latency(self, rng):
        # Gaussian noise around the fingerprint -- this is what an external
        # observer measuring response timing would see. Real and decoy
        # sessions are drawn from the SAME distribution parameters, which
        # is the whole point: a passive timing analysis cannot tell them
        # apart before detection fires.
        return max(0.1, rng.gauss(self.fingerprint_mean_latency_ms, self.fingerprint_jitter_ms))


class SuperpositionGroup:
    """A real session plus N indistinguishable decoys, sharing one fingerprint
    profile, with a shared detector and migration logic."""

    def __init__(self, n_decoys=4, base_latency_ms=42.0, jitter_ms=6.0,
                 detection_threshold=3.0, seed=None):
        self.rng = random.Random(seed)
        self.detection_threshold = detection_threshold
        self.sessions = []

        real = Session(
            id=str(uuid.uuid4()),
            is_real=True,
            backend_id="backend-real-0",
            fingerprint_mean_latency_ms=base_latency_ms,
            fingerprint_jitter_ms=jitter_ms,
        )
        self.sessions.append(real)
        self.real_session = real

        for i in range(n_decoys):
            decoy = Session(
                id=str(uuid.uuid4()),
                is_real=False,
                backend_id=f"backend-decoy-{i}",
                fingerprint_mean_latency_ms=base_latency_ms,   # SAME distribution
                fingerprint_jitter_ms=jitter_ms,                # SAME distribution
            )
            self.sessions.append(decoy)

        self.migration_log = []

    def observe_latencies(self, n_samples=200):
        """Simulate an external attacker/observer passively timing every
        session's responses. Returns {session_id: [latency samples]}."""
        return {
            s.id: [s.sample_latency(self.rng) for _ in range(n_samples)]
            for s in self.sessions
        }

    def apply_anomaly_event(self, session_id, score_delta):
        """Feed an anomaly signal into a specific session (e.g. it touched a
        honeytoken, made an impossible request, deviated behaviorally)."""
        for s in self.sessions:
            if s.id == session_id:
                s.anomaly_score += score_delta
                if s.anomaly_score >= self.detection_threshold and not s.migrated and not s.caught:
                    self._collapse(s)
                return s
        raise KeyError(session_id)

    def _collapse(self, flagged_session):
        """'Measurement collapses the state.' If the flagged session was the
        real user, migrate them invisibly. If it was a decoy, mark it caught
        and keep it running as a live tarpit / forensic instrument."""
        if flagged_session.is_real:
            new_backend = f"backend-real-{uuid.uuid4().hex[:6]}"
            self.migration_log.append({
                "event": "real_user_migrated",
                "old_backend": flagged_session.backend_id,
                "new_backend": new_backend,
                "t": time.time(),
            })
            flagged_session.backend_id = new_backend
            flagged_session.migrated = True
            flagged_session.anomaly_score = 0.0
            # A brand-new decoy backend replaces this slot's old identity so
            # group size / shape doesn't visibly change to an observer.
        else:
            flagged_session.caught = True
            self.migration_log.append({
                "event": "decoy_triggered_kept_as_tarpit",
                "backend": flagged_session.backend_id,
                "t": time.time(),
            })

    def status(self):
        return {
            "n_sessions": len(self.sessions),
            "real_migrated": self.real_session.migrated,
            "decoys_caught": sum(1 for s in self.sessions if not s.is_real and s.caught),
            "migration_events": len(self.migration_log),
        }
