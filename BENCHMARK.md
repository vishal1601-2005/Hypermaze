# Hyperbolic maze / decoy-clone deception system

A prototype and test-bed for a deception-technology idea: trap an attacker
in a lazily-generated maze embedded in hyperbolic space, while a
statistically-indistinguishable decoy layer protects the real user, and a
detection event triggers an invisible migration of the real user to clean
infrastructure.

This README is deliberately blunt about what's proven, what's a real
upgrade over standard practice, and what is NOT ready for production use.

## What's in this repo

| File | What it does |
|---|---|
| `hyperbolic_maze.py` | Core engine: exact Mobius-transform (SU(1,1)) embedding of a k-ary tree in the Poincare disk. |
| `render.py` | Renders the maze to a PNG for visual inspection. |
| `moving_target.py` | Compares isometric shifting of the maze against naive relabeling ("move the patch" idea). |
| `decoy_layer.py` | Real session + N indistinguishable decoy sessions, detection-triggered migration ("clone" idea). |
| `simulate.py` | Single-model attacker-walk simulation (resource cost vs. apparent maze size). |
| `benchmark.py` | Three-way benchmark: static honeypot (industry baseline) vs. lazy flat tree vs. full hyperbolic system. |
| `server.py` | Real asyncio TCP server you can `nc`/`telnet` into and explore. |
| `tests/` | 20 pytest tests covering the geometry, moving-target, and decoy-layer claims. |

## Running it

```bash
# from an Anaconda/conda env or system python3
pip install numpy matplotlib scipy pytest --break-system-packages   # if needed

# run the full test suite
python3 -m pytest tests/ -v

# run the benchmark
python3 benchmark.py

# run the moving-target comparison
python3 moving_target.py

# run the decoy indistinguishability check
python3 test_indistinguishability.py

# start the live server (separate terminal to connect)
python3 server.py
# then, from another terminal:
nc 127.0.0.1 8888
# commands once connected: look, go <n>, back, take <name>, status, quit
```

## The honest verdict: what's actually driving the benefit?

Your original idea bundled two genuinely different mechanisms together.
Separating them was the point of the three-way benchmark, and the result
matters:

### 1. Laziness (on-demand generation) — this is the big win, and it is NOT specific to hyperbolic geometry

Any tree-shaped honeypot, drawn in flat space or hyperbolic space or no
space at all, gets this if you only materialize a room when someone steps
into it. The benchmark shows:

- **Model A** (static, fixed-budget honeypot — representative of widely
  deployed decoy platforms): a **systematic attacker fully maps a bounded
  honeypot of any size in exactly N steps, 100% of the time.** A static
  honeypot is a finite object; patience alone defeats it.
- **Model B** (lazy flat tree, no geometry claims): real cost scales with
  attacker engagement (linear), and the maze structurally **cannot be
  fully mapped** — there's no fixed N to exhaust. This is true whether or
  not you use hyperbolic geometry.

If your actual goal was "make the honeypot cheap and unmappable," you
achieve that with laziness alone. Don't let anyone (including this
writeup, if you'd stopped reading here) credit hyperbolic geometry for a
win that comes from caching strategy.

### 2. Hyperbolic geometry specifically — real, but narrower than it first looks

Once laziness is controlled for, geometry earns its keep in exactly two
measured places:

- **Uniform high branching without distortion.** A flat 2D tiling can only
  keep every room looking identical (same number of doors, no visible
  seams) up to branching factor ~6 (hexagonal tiling) before it either
  stops being planar or has to distort room sizes as you go deeper.
  Hyperbolic space supports *any* branching factor with perfectly uniform
  local geometry. This matters if realism (every room looking like a
  normal, undistorted room) is part of your deception.
- **Isometric shifting is provably non-detectable; naive shuffling is not.**
  This is the sharpest, most measurable result in this repo:
  - Isometric shift (apply a Mobius transform to the whole patch):
    **mean distance-consistency error = 0.00000000**
  - Naive relabeling (randomly reassign which backend serves which room):
    **mean distance-consistency error ≈ 2.4–2.5** (max error > 10)

  If an attacker has measured relative distances (via RTT, hop count, or
  any other consistent metric) between rooms before a shift, an isometric
  shift leaves every one of those measurements exactly correct afterward.
  Naive relabeling does not — it's internally inconsistent and therefore
  detectable as tampering, even without an external reference point. This
  is the one place where "use actual hyperbolic geometry" beats "just
  randomize things" in a way you can put a number on.

### 3. The decoy/clone layer — real, measured, works as described

Across 200 Monte Carlo trials, decoys built with the same latency
fingerprint as the real session were caught by a Kolmogorov-Smirnov test
at almost exactly the 5% rate you'd expect from random noise alone
(measured: 4.6%, expected under "truly indistinguishable": 5%). A
deliberately mismatched decoy, by contrast, was caught with p < 0.000001
— confirming the test has real power and isn't just failing to notice
anything. Detection-triggered migration correctly distinguishes "flag was
on the real session → migrate invisibly" from "flag was on a decoy →
keep it running as an instrumented tarpit," and the group's visible shape
never changes size when this happens.

## Validation history

Beyond the automated test suite, this system has been exercised against escalating levels of real-world conditions:

| Milestone | Status | Notes |
|---|---|---|
| Unit tests (geometry, isometry, decoy layer) | ✅ Done | 20/20 passing, deterministic, reproducible across machines |
| Live server, manual single-user exploration | ✅ Done | Confirmed detection fires correctly on honeytoken pickup |
| Concurrency hardening | ✅ Done | 300 simultaneous connection attempts, 0 crashes; connection limits (global + per-IP) enforced correctly |
| Fuzz/malformed-input hardening | ✅ Done | 17 adversarial payloads (oversized input, binary garbage, injection-shaped strings, slowloris-style no-newline data) — 0 unhandled exceptions after a real bug fix (Python's `readline()` silently converts its own `LimitOverrunError` into a bare `ValueError`, which the first hardening pass didn't catch) |
| Real network hop (LAN, cross-device) | ✅ Done | Server exposed via Windows port-forwarding (`netsh portproxy`) + firewall rule from a WSL2 host, reached over real WiFi from a second physical device on a mobile hotspot network, using an independent TCP client app (not the same tooling used for local testing). Exploration and honeytoken detection both confirmed working end-to-end over this path. |
| Open-internet exposure | ❌ Not done | No public/cloud deployment yet — see "What this is NOT (yet)" below |
| Independent red-teaming | ❌ Not done | All attacker models used so far were written by the same people who wrote the defense |

The LAN test is a genuine, if modest, real-world validation step: it's the first time any part of this system was reached by a device other than the one it runs on, across a real wireless hop and a real NAT/firewall path, rather than over loopback. It does not substitute for open-internet exposure (different threat model entirely — background-radiation scanning, real adversarial traffic, no assumption of a trusted local network) or for review by anyone who didn't build the thing.

## What this is NOT (yet)

- **Not a hardened, deployable security product.** No auth, no TLS, no
  rate limiting beyond the connection caps and idle timeout added during
  hardening, no integration with a real IDS, SDN controller, or
  session-migration fabric. The server has been validated over a real LAN
  hop (see "Validation history" above) but never exposed to the open
  internet — treat it as a tested research/demo tool for an isolated or
  monitored network, not a production-ready public service.
- **Not independently red-teamed.** Everything here is validated against
  the attacker models we wrote ourselves (random walk, systematic DFS).
  A real adversary might have strategies these simulations don't capture
  (e.g. timing side-channels beyond the ones we modeled, or protocol-level
  fingerprinting we didn't simulate).
- **Not a replacement for existing deception platforms** — it's an
  architecture that could sit *inside* one, specifically for the maze
  containment layer and the moving-target layer. Real deployment would
  mean integrating with actual network infrastructure (SDN for the
  session migration, a real IDS/anomaly detector instead of a scripted
  honeytoken trigger, and a proper multi-tenant resource governor instead
  of the hardcoded 20,000-room cap per session).

## Bottom line

The idea is real and the parts that are specifically about hyperbolic
geometry (not just "cache aggressively") survive rigorous testing: the
isometric-shift result in particular is a clean, provable, quantifiable
advantage over naive moving-target defenses that's worth taking further.
The laziness/unboundedness win is enormous but belongs to the "lazy
generation" idea in general, not to the hyperbolic framing specifically —
still very much worth having, just correctly attributed.
