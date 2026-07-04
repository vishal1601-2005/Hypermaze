"""
tools/concurrency_test.py

Spawns N simultaneous real TCP clients against a running server instance
and drives each through a random walk of M steps, concurrently. Distinguishes
three outcomes per client:
  - ok: completed all steps successfully
  - rejected_cleanly: server correctly enforced a connection limit (this is
    a PASS, not a failure -- it means the hardening is working)
  - actual_failure: anything else (timeout, crash, garbage response)

Usage:
    python3 server.py &        # start the server first, separate process
    python3 tools/concurrency_test.py --clients 100 --steps 30
"""

import argparse
import asyncio
import random
import time

REJECTION_MESSAGES = (b"server busy", b"too many connections")


async def run_one_client(client_id, host, port, steps, results):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            first_chunk = await asyncio.wait_for(reader.read(200), timeout=3)
        except asyncio.TimeoutError:
            results[client_id] = {"status": "actual_failure", "error": "no initial response", "steps_ok": 0}
            writer.close()
            return

        if any(msg in first_chunk for msg in REJECTION_MESSAGES):
            results[client_id] = {"status": "rejected_cleanly", "error": None, "steps_ok": 0}
            writer.close()
            return

        # otherwise keep reading until we see the first prompt
        buf = first_chunk
        while b"> " not in buf:
            chunk = await asyncio.wait_for(reader.read(200), timeout=3)
            if not chunk:
                break
            buf += chunk

        rng = random.Random(client_id)
        ok_steps = 0
        for _ in range(steps):
            cmd = rng.choice(["look", "go 0", "go 1", "go 2", "go 3", "back", "status"])
            writer.write((cmd + "\n").encode())
            await writer.drain()
            try:
                data = await asyncio.wait_for(reader.readuntil(b"> "), timeout=5)
            except asyncio.TimeoutError:
                results[client_id] = {"status": "actual_failure", "error": "response timeout", "steps_ok": ok_steps}
                writer.close()
                return
            if not data:
                results[client_id] = {"status": "actual_failure", "error": "connection closed early", "steps_ok": ok_steps}
                return
            ok_steps += 1

        writer.write(b"quit\n")
        await writer.drain()
        writer.close()
        results[client_id] = {"status": "ok", "error": None, "steps_ok": ok_steps}
    except Exception as e:
        results[client_id] = {"status": "actual_failure", "error": repr(e), "steps_ok": 0}


async def main(host, port, n_clients, steps):
    results = {}
    start = time.time()
    tasks = [run_one_client(i, host, port, steps, results) for i in range(n_clients)]
    await asyncio.gather(*tasks)
    elapsed = time.time() - start

    n_ok = sum(1 for r in results.values() if r["status"] == "ok")
    n_rejected = sum(1 for r in results.values() if r["status"] == "rejected_cleanly")
    n_fail = sum(1 for r in results.values() if r["status"] == "actual_failure")

    print(f"=== Concurrency test: {n_clients} simultaneous clients, {steps} steps each ===")
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Succeeded fully: {n_ok}/{n_clients}")
    print(f"Cleanly rejected (limit enforcement working as designed): {n_rejected}/{n_clients}")
    print(f"Actual failures (crash/timeout/garbage): {n_fail}/{n_clients}")

    if n_fail:
        print("\nFailure details (first 10):")
        shown = 0
        for cid, r in results.items():
            if r["status"] == "actual_failure":
                print(f"  client {cid}: {r['error']} (completed {r['steps_ok']}/{steps} steps)")
                shown += 1
                if shown >= 10:
                    break

    return n_fail == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--clients", type=int, default=100)
    ap.add_argument("--steps", type=int, default=30)
    args = ap.parse_args()

    ok = asyncio.run(main(args.host, args.port, args.clients, args.steps))
    exit(0 if ok else 1)
