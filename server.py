"""
server.py

A real, runnable TCP server you can connect to with `nc localhost 8888` or
`telnet localhost 8888`. Every connection is dropped into the hyperbolic
maze at the entry point (the "origin" room). Commands:

    look                 -- show current room and its doors
    go <door_number>     -- move through a door (materializes the room
                             lazily if it hasn't been visited before)
    back                 -- go back to the previous room
    take <token>         -- attempt to take an item -- some rooms contain
                             a "honeytoken" file; taking it fires detection
    status               -- show your session id, rooms visited, depth
    quit                 -- disconnect

This is a genuine, testable prototype of the deception concept. It has
been hardened against the concrete failure modes a network service should
survive by default -- connection flooding, per-IP abuse, idle/slowloris
connections, and malformed/oversized input -- and that hardening is
verified in tools/concurrency_test.py and tools/fuzz_test.py. It has NOT
been hardened against everything a production deployment needs: no TLS,
no authentication, no integration with a real IDS. Treat it as a tested
research/demo server to run in an isolated environment (a VM, a
container, or a monitored network segment), not blindly on the open
internet without understanding what "open internet" actually exposes it to.

Run it:
    python3 server.py

Connect to it (from another terminal):
    nc localhost 8888
    (or) telnet localhost 8888
"""

import asyncio
import os
import random
import uuid
import logging
from collections import defaultdict

import hyperbolic_maze as hm
import local_cycles
from decoy_layer import SuperpositionGroup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hypermaze-server")

BRANCHING = 4
EDGE_LENGTH = 1.1
HONEYTOKEN_PROBABILITY = 0.15   # fraction of rooms that contain a trap item
MAX_ROOMS_PER_SESSION = 20000   # hard safety cap on lazy materialization per connection

# --- hardening knobs -------------------------------------------------------
# Configurable via env vars so tests can isolate each property (e.g. testing
# raw concurrency without every simulated client tripping the per-IP cap,
# since real tests typically all originate from 127.0.0.1).
MAX_TOTAL_CONNECTIONS = int(os.environ.get("HYPERMAZE_MAX_TOTAL", "200"))
MAX_CONNECTIONS_PER_IP = int(os.environ.get("HYPERMAZE_MAX_PER_IP", "5"))
IDLE_TIMEOUT_SECONDS = int(os.environ.get("HYPERMAZE_IDLE_TIMEOUT", "120"))
READ_LINE_LIMIT_BYTES = int(os.environ.get("HYPERMAZE_MAX_LINE_BYTES", "4096"))
# ---------------------------------------------------------------------------

_connections_by_ip = defaultdict(int)
_total_connections = 0
_conn_lock = asyncio.Lock()


class MazeSession:
    """One connected client's view into the maze. Each connection gets its
    own lazily-materialized tree rooted at a fresh origin, so no client can
    exhaust another client's resources and no client can pre-map another
    client's maze (their branchings/edge choices are independently random-
    seeded per session).

    Each room's doors now include both its own children (new, unexplored
    territory) AND local ring links to its siblings (already-materialized
    rooms from the same parent). Both kinds of door look identical from
    the "look" output -- there's no way to tell, without walking through
    one, whether a given door leads somewhere new or loops back to
    already-explored territory. This also fixes a real structural
    weakness of a pure tree: previously every room had exactly one path
    back to the entry point; now there are local redundant paths, which
    is what a real network/building actually looks like."""

    def __init__(self, session_id):
        self.session_id = session_id
        self.rng = random.Random()
        self.root = hm.make_root()
        self.materialized = {self.root.id: self.root}
        self._next_id = 1
        self.current = self.root
        self.honeytokens = {}   # node_id -> token name, assigned lazily
        self.ring_links = {}    # node_id -> list of sibling node_ids
        self.anomaly_score = 0.0
        self.caught = False

        # Each session gets its own decoy group representing the "clone"
        # layer -- in a real deployment this would sit on the legitimate
        # user's side, not the maze explorer's side, but we expose its
        # state here so you can see it operating during the demo.
        self.decoys = SuperpositionGroup(n_decoys=4, seed=self.rng.randint(0, 1_000_000))

    def _expand(self, node):
        if not node.children and len(self.materialized) < MAX_ROOMS_PER_SESSION:
            children, self._next_id = hm.expand_node(node, BRANCHING, EDGE_LENGTH, self._next_id)
            for c in children:
                self.materialized[c.id] = c
                if self.rng.random() < HONEYTOKEN_PROBABILITY:
                    self.honeytokens[c.id] = self.rng.choice(
                        ["admin_credentials.txt", "backup_keys.pem", "customer_db.sql", "root_shell.sh"]
                    )
            # Wire this sibling group into a local ring -- fully computable
            # from just these children, no knowledge of any other branch
            # needed, so this stays compatible with lazy generation.
            ring = local_cycles.wire_local_ring(children)
            for node_id, neighbor_ids in ring.items():
                self.ring_links.setdefault(node_id, []).extend(neighbor_ids)
        return node.children

    def _doors(self, node):
        """Combined list of reachable rooms from this node: its own
        children (via _expand, lazily materialized) plus any ring-linked
        siblings (already materialized, no expansion needed)."""
        children = self._expand(node)
        ring_neighbor_ids = self.ring_links.get(node.id, [])
        ring_neighbors = [self.materialized[nid] for nid in ring_neighbor_ids]
        return list(children) + ring_neighbors

    def look(self):
        doors = self._doors(self.current)
        lines = [
            f"You are in room #{self.current.id} (depth {self.current.depth}).",
            f"Doors: {len(doors)}" + (" (dead end)" if not doors else ""),
        ]
        if self.current.id in self.honeytokens:
            lines.append(f"There is a file here: {self.honeytokens[self.current.id]}")
        return "\n".join(lines)

    def go(self, door_index):
        doors = self._doors(self.current)
        if door_index < 0 or door_index >= len(doors):
            return "There is no door there."
        self.current = doors[door_index]
        return self.look()

    def back(self):
        if self.current.parent is None:
            return "You are already at the entry point."
        self.current = self.current.parent
        return self.look()

    def take(self, name):
        token = self.honeytokens.get(self.current.id)
        if token is None:
            return "There is nothing here to take."
        if name != token:
            return f"There is no '{name}' here."
        self.anomaly_score += 5.0
        self.decoys.apply_anomaly_event(self.decoys.real_session.id, 0.0)
        if self.anomaly_score >= 5.0 and not self.caught:
            self.caught = True
            log.warning(f"[{self.session_id}] DETECTION: honeytoken '{token}' taken in room "
                        f"#{self.current.id} at depth {self.current.depth}. Session flagged.")
            return (f"You take {token}.\n"
                    f"[SYSTEM]: anomaly detected -- this session is now flagged and instrumented.")
        return f"You take {token}."

    def status(self):
        total_ring_links = sum(len(v) for v in self.ring_links.values()) // 2
        return "\n".join([
            f"session: {self.session_id}",
            f"rooms materialized this session: {len(self.materialized)}",
            f"local ring links (redundant paths): {total_ring_links}",
            f"current depth: {self.current.depth}",
            f"flagged: {self.caught}",
        ])


def _handle_command(session, cmd):
    """Parse and execute one command line. Isolated from the network loop
    so it can never raise a network-layer exception, and so it's directly
    unit-testable without a socket."""
    parts = cmd.split()
    if not parts:
        return None
    op = parts[0].lower()

    try:
        if op == "quit":
            return "__QUIT__"
        elif op == "look":
            return session.look()
        elif op == "go" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
            if len(parts[1]) > 9:
                return "invalid door number."
            return session.go(int(parts[1]))
        elif op == "back":
            return session.back()
        elif op == "take" and len(parts) >= 2:
            return session.take(" ".join(parts[1:]))
        elif op == "status":
            return session.status()
        else:
            return "unknown command. try: look, go <n>, back, take <name>, status, quit"
    except Exception:
        log.exception(f"[{session.session_id}] error handling command: {cmd!r}")
        return "internal error handling that command."


async def handle_client(reader, writer):
    global _total_connections
    peer = writer.get_extra_info("peername")
    peer_ip = peer[0] if peer else "unknown"
    session_id = str(uuid.uuid4())[:8]

    async with _conn_lock:
        if _total_connections >= MAX_TOTAL_CONNECTIONS:
            writer.write(b"server busy, try again later.\n")
            await writer.drain()
            writer.close()
            log.warning(f"[{session_id}] rejected: global connection cap reached "
                        f"({MAX_TOTAL_CONNECTIONS})")
            return
        if _connections_by_ip[peer_ip] >= MAX_CONNECTIONS_PER_IP:
            writer.write(b"too many connections from your address.\n")
            await writer.drain()
            writer.close()
            log.warning(f"[{session_id}] rejected: per-IP cap reached for {peer_ip} "
                        f"({MAX_CONNECTIONS_PER_IP})")
            return
        _total_connections += 1
        _connections_by_ip[peer_ip] += 1

    session = MazeSession(session_id)
    log.info(f"[{session_id}] connection from {peer} "
             f"(total={_total_connections}, from_this_ip={_connections_by_ip[peer_ip]})")

    try:
        banner = (
            "== hyperbolic maze demo server ==\n"
            "commands: look, go <n>, back, take <name>, status, quit\n"
            + session.look() + "\n"
        )
        writer.write(banner.encode())
        await writer.drain()

        while True:
            writer.write(b"> ")
            await writer.drain()

            try:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                writer.write(b"\nidle timeout, disconnecting.\n")
                await writer.drain()
                break
            except (asyncio.LimitOverrunError, ValueError):
                # asyncio.StreamReader.readline() internally raises
                # LimitOverrunError but re-raises it as a bare ValueError
                # before it reaches caller code -- both are handled the
                # same way here: the line was too long, disconnect cleanly.
                writer.write(b"\nline too long, disconnecting.\n")
                await writer.drain()
                break

            if not line:
                break

            if len(line) > READ_LINE_LIMIT_BYTES:
                writer.write(b"line too long, disconnecting.\n")
                await writer.drain()
                break

            cmd = line.decode(errors="ignore").strip()
            if not cmd:
                continue

            out = _handle_command(session, cmd)
            if out is None:
                continue
            if out == "__QUIT__":
                writer.write(b"bye\n")
                break

            writer.write((out + "\n").encode())
            await writer.drain()

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    except Exception:
        log.exception(f"[{session_id}] unexpected error in connection handler")
    finally:
        log.info(f"[{session_id}] disconnected. rooms materialized: {len(session.materialized)}, "
                  f"flagged: {session.caught}")
        try:
            writer.close()
        except Exception:
            pass
        async with _conn_lock:
            _total_connections -= 1
            _connections_by_ip[peer_ip] -= 1
            if _connections_by_ip[peer_ip] <= 0:
                del _connections_by_ip[peer_ip]


async def main(host="127.0.0.1", port=8888):
    server = await asyncio.start_server(
        handle_client, host, port, limit=READ_LINE_LIMIT_BYTES * 2
    )
    addr = server.sockets[0].getsockname()
    log.info(f"hyperbolic maze demo server listening on {addr[0]}:{addr[1]}")
    log.info(f"limits: max_total={MAX_TOTAL_CONNECTIONS}, max_per_ip={MAX_CONNECTIONS_PER_IP}, "
             f"idle_timeout={IDLE_TIMEOUT_SECONDS}s, max_line={READ_LINE_LIMIT_BYTES}B")
    log.info("connect with: nc {} {}".format(addr[0], addr[1]))
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
