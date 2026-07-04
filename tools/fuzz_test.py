"""
tools/fuzz_test.py

Sends a battery of malformed, oversized, and adversarial payloads at the
server and checks: (1) the server never crashes, (2) it responds sanely
(or disconnects cleanly) to each, and (3) a normal client can still
connect and get a normal response AFTER all the abuse -- proving the
server survived, not just that one connection died gracefully.

Usage:
    python3 server.py &
    python3 tools/fuzz_test.py
"""

import asyncio
import sys


async def send_and_check(host, port, payload, description, read_timeout=2):
    if description == "immediately close with zero bytes sent":
        # This case specifically tests: does the server handle a client
        # connecting and disconnecting without ever sending data? There is
        # nothing to "respond" to here -- the correct behavior is simply
        # not hanging or crashing, which we confirm via the health check
        # afterward, not by waiting for a response that was never coming.
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True, "connected and disconnected immediately, no crash"
        except Exception as e:
            return True, f"connection-level exception (acceptable): {e!r}"

    try:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await asyncio.wait_for(reader.read(500), timeout=read_timeout)  # banner
        except asyncio.TimeoutError:
            pass

        writer.write(payload)
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            return True, "connection reset on write (acceptable for garbage input)"

        try:
            resp = await asyncio.wait_for(reader.read(1000), timeout=read_timeout)
        except asyncio.TimeoutError:
            return False, "TIMED OUT waiting for any response (possible hang)"
        except (ConnectionResetError, BrokenPipeError):
            return True, "connection reset (acceptable)"

        writer.close()
        return True, f"responded with {len(resp)} bytes, no hang"
    except Exception as e:
        return True, f"connection-level exception (acceptable): {e!r}"


async def check_server_still_healthy(host, port):
    """After all the fuzzing, confirm a normal client still gets a normal
    response -- the real test of survival."""
    try:
        reader, writer = await asyncio.open_connection(host, port)
        await asyncio.wait_for(reader.readuntil(b"> "), timeout=3)
        writer.write(b"look\n")
        await writer.drain()
        resp = await asyncio.wait_for(reader.readuntil(b"> "), timeout=3)
        writer.write(b"quit\n")
        await writer.drain()
        writer.close()
        return b"room" in resp.lower() or b"You are in room" in resp
    except Exception as e:
        print(f"  SERVER HEALTH CHECK FAILED: {e!r}")
        return False


PAYLOADS = [
    (b"\n", "empty line"),
    (b"go\n", "go with no argument"),
    (b"go abc\n", "go with non-numeric argument"),
    (b"go -999999999999999999999999999\n", "go with absurdly large negative number"),
    (b"go 99999999999999999999999999999999\n", "go with absurdly large positive number"),
    (b"go " + b"9" * 100000 + b"\n", "go with a 100,000-digit number"),
    (b"\x00\x01\x02\x03\xff\xfe" * 100 + b"\n", "raw binary garbage"),
    ("look 日本語 emoji 🎉🔥💀\n".encode("utf-8"), "unicode/emoji input"),
    (b"A" * 200000, "200KB of data with no newline at all (buffer/slowloris style)"),
    (b"take " + b"x" * 50000 + b"\n", "extremely long take argument"),
    (b"look\r\nlook\r\ngo 0\r\n", "CRLF line endings instead of LF"),
    (b"", "immediately close with zero bytes sent"),
    (b"\n\n\n\n\n\n\n\n\n\n", "many blank lines"),
    (b"quit\nlook\n", "commands after quit"),
    (b"GO 0\nLOOK\nSTATUS\n", "uppercase commands"),
    (b"go 0; rm -rf /\n", "shell-injection-style payload (should just be treated as garbage args)"),
    (b"' OR '1'='1\n", "SQL-injection-style payload (no DB here, but checking it's inert)"),
]


async def main(host="127.0.0.1", port=8888):
    print(f"=== Fuzz test: {len(PAYLOADS)} adversarial payloads against {host}:{port} ===\n")
    all_ok = True
    for payload, desc in PAYLOADS:
        ok, detail = await send_and_check(host, port, payload, desc)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {desc}: {detail}")
        if not ok:
            all_ok = False

    print("\n=== Post-fuzz health check ===")
    healthy = await check_server_still_healthy(host, port)
    print(f"Server still responds normally after all fuzzing: {'YES' if healthy else 'NO -- SERVER DEGRADED'}")

    overall_ok = all_ok and healthy
    print(f"\nOVERALL: {'PASS' if overall_ok else 'FAIL'}")
    return overall_ok


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
