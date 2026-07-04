# hypermaze

**A honeypot maze embedded in hyperbolic space, with an indistinguishable decoy layer and a provably undetectable moving-target defense.**

![hyperbolic maze render](maze.png)

Most deception platforms deploy a fixed pool of decoy hosts. A patient attacker can fully map a fixed pool — deterministically, in exactly N steps, regardless of N. This project asks a narrower, more interesting question: what if the maze isn't a *fixed graph* but a *space*, generated lazily as the attacker moves through it, with geometry chosen specifically so that shifting the whole thing later leaves no detectable seam?

Three claims are made here. All three are backed by a test suite and a reproducible benchmark, not just a diagram.

| Claim | Result |
|---|---|
| Lazy generation makes the maze unmappable | A systematic attacker fully maps a static N-node honeypot 100% of the time, in exactly N steps. A lazily-generated tree cannot be fully mapped — there is no fixed N. |
| Hyperbolic isometries make a "moving target" shift undetectable | Isometric shift: **0.00000000** mean distance-consistency error. Naive relabeling: **2.48** mean error (max **10.62**). |
| Decoy sessions are statistically indistinguishable from the real one | Empirical false-positive rate under a Kolmogorov–Smirnov test: **4.6%**, against a theoretical ~5% for two samples drawn from the *same* distribution. A deliberately mismatched decoy is caught at p < 10⁻⁶, confirming the test has power. |

---

## The idea, in one paragraph

A regular tree with branching factor *k* has *k*(*k*−1)^(*d*−1) nodes at depth *d* — exponential. You cannot embed that in flat space without either distorting room sizes as you go deeper or capping the branching factor at ~6 (the largest regular flat tiling). Hyperbolic space supports a uniform tiling — every room looking identical, undistorted — at *any* branching factor, because the space itself has negative curvature. That single geometric fact underwrites two defensive properties: rooms can be generated lazily on demand (paying real compute only for what the attacker actually visits, since there is no bound to precompute against), and the entire local patch can be "moved" via a hyperbolic isometry — a transform that preserves every pairwise distance exactly, so nothing an attacker measured before the shift becomes inconsistent afterward.

Layered on top: every legitimate user session is accompanied by *N* decoy sessions built from the same latency/fingerprint distribution. Nothing is distinguishable from the outside until an anomaly detector fires. At that point the system "collapses" — if the flagged session was real, it's migrated invisibly to fresh infrastructure; if it was a decoy, it's kept alive as an instrumented tarpit.

---

## Architecture

```
hyperbolic_maze.py    Core engine — exact SU(1,1) Mobius-transform embedding
                       of a k-ary tree in the Poincare disk model.
moving_target.py       Isometric shift vs. naive relabeling — the
                       moving-target defense, benchmarked against itself.
decoy_layer.py         Real session + N indistinguishable decoys,
                       detection-triggered migration.
server.py               A real asyncio TCP server exposing the maze as a
                       navigable protocol — connect with `nc`/`telnet`.
benchmark.py            Three-way comparison: static fixed-budget honeypot
                       (industry baseline) vs. lazy flat tree (isolates
                       laziness) vs. the full hyperbolic system.
tests/                  20 pytest tests covering the geometry, the
                       isometry-preservation proof, and the decoy layer.
```

---

## Quickstart

```bash
git clone https://github.com/<your-username>/hypermaze.git
cd hypermaze
python3 -m venv hypermaze_env
source hypermaze_env/bin/activate
pip install -r requirements.txt

# verify the math
python3 -m pytest tests/ -v          # 20 passed

# see the isometry proof
python3 moving_target.py

# see the decoy indistinguishability test
python3 test_indistinguishability.py

# run the three-way benchmark against a static-honeypot baseline
python3 benchmark.py

# render the maze
python3 render.py

# talk to a live instance
python3 server.py &
nc 127.0.0.1 8888
```

Once connected to the server: `look`, `go <n>`, `back`, `take <filename>`, `status`, `quit`.

---

## What the benchmark actually isolates

The interesting engineering question isn't "is this a good idea" in the abstract — it's *which part* of the idea is doing the work. The benchmark separates two effects that are easy to conflate:

**Laziness** (materializing a room only when the attacker steps into it) is the larger effect, and it has nothing to do with hyperbolic geometry specifically — any on-demand tree gets it. A static, pre-built honeypot of any size is a *finite object*; a systematic attacker maps it completely in exactly N steps, every time. A lazily-generated tree has no such N.

**Hyperbolic geometry specifically** earns its keep in one measurable place: moving-target shifts. An isometry of the Poincaré disk preserves every pairwise hyperbolic distance exactly — so if an attacker has fingerprinted relative distances between rooms (via RTT, hop count, or any consistent metric) before a shift, every one of those measurements is still exactly true afterward. There is no internal inconsistency to detect. A naive "shuffle which backend serves which address" approach has no such guarantee, and the benchmark shows it: error jumps from 0 to a mean of 2.48 (max 10.62).

Full breakdown — including the specific attacker models used (random walk and systematic DFS), the static-honeypot baseline, and result tables — is in [`BENCHMARK.md`](BENCHMARK.md).

---

## Honest limitations

This is a tested, reproducible research prototype — not a hardened product.

- No auth, TLS, or rate limiting on the demo server. Run it in an isolated environment (a VM, a container, or localhost), not on the open internet.
- The attacker models here (random walk, systematic DFS) are the ones we could rigorously define and test. A real adversary may have strategies — timing side-channels, protocol fingerprinting — this repo doesn't simulate.
- The decoy/migration layer here is a clean simulation of the logic (session objects, timing distributions). Wiring it into a real SDN controller, IDS, and session-migration fabric is a separate, substantial engineering project.
- Not independently red-teamed.

If you're picking this up for a real deployment, treat the maze-containment and moving-target pieces as a candidate architecture to integrate into an existing deception platform, not a drop-in replacement for one.

---

## License

MIT — see [LICENSE](LICENSE).
