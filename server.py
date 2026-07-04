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

This is a genuine, testable prototype of the deception concept -- NOT a
hardened production security product. It has no authentication, TLS, rate
limiting, or resource caps beyond what's coded here. Treat it as a research
/ demo server to run in an isolated environment (a VM, a container, or just
localhost), not something to expose to the open internet.

Run it:
    python3 server.py

Connect to it (from another terminal):
    nc localhost 8888
    (or) telnet localhost 8888
"""

import asyncio
import random
import uuid
import logging

import hyperbolic_maze as hm
from decoy_layer import SuperpositionGroup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hypermaze-server")

BRANCHING = 4
EDGE_LENGTH = 1.1
HONEYTOKEN_PROBABILITY = 0.15   # fraction of rooms that contain a trap item
MAX_ROOMS_PER_SESSION = 20000   # hard safety cap on lazy materialization per connection


class MazeSession:
    """One connected client's view into the maze. Each connection gets its
    own lazily-materialized tree rooted at a fresh origin, so no client can
    exhaust another client's resources and no client can pre-map another
    client's maze (their branchings/edge choices are independently random-
    seeded per session)."""

    def __init__(self, session_id):
        self.session_id = session_id
        self.rng = random.Random()
        self.root = hm.make_root()
        self.materialized = {self.root.id: self.root}
        self._next_id = 1
        self.current = self.root
        self.honeytokens = {}   # node_id -> token name, assigned lazily
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
        return node.children

    def look(self):
        children = self._expand(self.current)
        lines = [
            f"You are in room #{self.current.id} (depth {self.current.depth}).",
            f"Doors: {len(children)}" + (" (dead end)" if not children else ""),
        ]
        if self.current.id in self.honeytokens:
            lines.append(f"There is a file here: {self.honeytokens[self.current.id]}")
        return "\n".join(lines)

    def go(self, door_index):
        children = self._expand(self.current)
        if door_index < 0 or door_index >= len(children):
            return "There is no door there."
        self.current = children[door_index]
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
        # Taking a honeytoken is a strong anomaly signal.
        self.anomaly_score += 5.0
        self.decoys.apply_anomaly_event(self.decoys.real_session.id, 0.0)  # no-op on real side
        if self.anomaly_score >= 5.0 and not self.caught:
            self.caught = True
            log.warning(f"[{self.session_id}] DETECTION: honeytoken '{token}' taken in room "
                        f"#{self.current.id} at depth {self.current.depth}. Session flagged.")
            return (f"You take {token}.\n"
                    f"[SYSTEM]: anomaly detected -- this session is now flagged and instrumented.")
        return f"You take {token}."

    def status(self):
        return "\n".join([
            f"session: {self.session_id}",
            f"rooms materialized this session: {len(self.materialized)}",
            f"current depth: {self.current.depth}",
            f"flagged: {self.caught}",
        ])


async def handle_client(reader, writer):
    session_id = str(uuid.uuid4())[:8]
    session = MazeSession(session_id)
    peer = writer.get_extra_info("peername")
    log.info(f"[{session_id}] connection from {peer}")

    banner = (
        "== hyperbolic maze demo server ==\n"
        "commands: look, go <n>, back, take <name>, status, quit\n"
        + session.look() + "\n"
    )
    writer.write(banner.encode())
    await writer.drain()

    try:
        while True:
            writer.write(b"> ")
            await writer.drain()
            line = await reader.readline()
            if not line:
                break
            cmd = line.decode(errors="ignore").strip()
            if not cmd:
                continue

            parts = cmd.split()
            op = parts[0].lower()

            if op == "quit":
                writer.write(b"bye\n")
                break
            elif op == "look":
                out = session.look()
            elif op == "go" and len(parts) == 2 and parts[1].isdigit():
                out = session.go(int(parts[1]))
            elif op == "back":
                out = session.back()
            elif op == "take" and len(parts) >= 2:
                out = session.take(" ".join(parts[1:]))
            elif op == "status":
                out = session.status()
            else:
                out = "unknown command. try: look, go <n>, back, take <name>, status, quit"

            writer.write((out + "\n").encode())
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        log.info(f"[{session_id}] disconnected. rooms materialized: {len(session.materialized)}, "
                  f"flagged: {session.caught}")
        writer.close()


async def main(host="127.0.0.1", port=8888):
    server = await asyncio.start_server(handle_client, host, port)
    addr = server.sockets[0].getsockname()
    log.info(f"hyperbolic maze demo server listening on {addr[0]}:{addr[1]}")
    log.info("connect with: nc {} {}".format(addr[0], addr[1]))
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
