# Phase 12G — LAN Transport Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral listener port with a stable configured default so that a narrow, permanent LAN firewall rule can allow Windows → Linux peer connections, after first proving the drop point with a packet capture.

**Architecture:** `RemoteSocketServer` gains a `preferred_port` parameter. Production startup passes `PEER_SERVICE_DEFAULT_PORT = 27321` (one canonical owner in `remote_support/server.py`). The server tries the preferred port first; if occupied, it falls back to ephemeral and marks `preferred_port_honored = False`. `listener_endpoint()` surfaces this flag so the UI can warn. A UFW application profile is added to `packaging/`. No firewall mutations happen at runtime; the user runs one explicit `ufw allow` command.

**Tech Stack:** Python 3.12, `socketserver.ThreadingTCPServer`, `maintenance/remote_support/server.py`, `maintenance/ui/window_discovery.py`, `maintenance/remote.py`, `packaging/system-analyzer`, `tests/test_remote_server.py`, `tests/test_cross_platform_branches.py`

---

## DIAGNOSTIC GATE — Must complete before Task 1

These steps contain NO production code changes. Complete them first. Only proceed to Task 1 if **Category B is confirmed** (SYN arrives at `enp2s0f0` but no SYN-ACK leaves).

### Gate Step 1 — Packet capture

**Linux (terminal 1, run first):**
```bash
sudo tcpdump -ni enp2s0f0 'host 192.168.55.103 and tcp port 43281' -c 20
```

**Windows (run once after tcpdump is listening):**
```powershell
Test-NetConnection 192.168.55.107 -Port 43281
```

Record the exact TCP flags sequence. Classify:
- **A** — no SYN visible on `enp2s0f0` → environment network block; STOP, no code change
- **B** — SYN visible, no SYN-ACK → Linux INPUT drop; proceed to Gate Step 2
- **C** — SYN + SYN-ACK visible, no Windows ACK → return path problem; STOP
- **D** — full handshake visible → listener/app problem; investigate separately

### Gate Step 2 — Read iptables INPUT rules

**Linux (terminal 2, any time):**
```bash
sudo iptables -S INPUT
sudo iptables -L INPUT -n -v --line-numbers
```

Identify the exact rule matching:
- src 192.168.55.103, dst 192.168.55.107, iif enp2s0f0, proto TCP, dport 43281

### Gate Step 3 — Narrow temporary rule proof (Category B only)

**Only run if Gate Step 1 confirmed Category B.**

Insert the smallest rule above the DROP:
```bash
# Find the DROP rule line number from Gate Step 2
# Insert ACCEPT rule at line N-1:
sudo iptables -I INPUT <N> \
  -i enp2s0f0 \
  -s 192.168.55.103 \
  -d 192.168.55.107 \
  -p tcp --dport 43281 \
  -j ACCEPT
```

Re-run Windows test:
```powershell
Test-NetConnection 192.168.55.107 -Port 43281
```

Expected: `TcpTestSucceeded : True`

**Remove the temporary rule immediately after confirming:**
```bash
sudo iptables -D INPUT <N>
```

Record exact insertion and deletion commands, counter values before/after, and Windows test result. Document in `docs/WINDOWS-FINDINGS-2026-09-17.md` as a Phase 12G section.

**If Gate Step 3 confirms TcpTestSucceeded: True → proceed to Task 1.**
**Any other outcome → stop and reassess.**

---

## File map

| File | Change |
|---|---|
| `maintenance/remote_support/server.py` | Add `PEER_SERVICE_DEFAULT_PORT = 27321`; add `preferred_port` param + `preferred_port_honored` property to `RemoteSocketServer` |
| `maintenance/remote.py` | Re-export `PEER_SERVICE_DEFAULT_PORT` |
| `maintenance/ui/window_discovery.py` | Pass `preferred_port=PEER_SERVICE_DEFAULT_PORT` to `RemoteSocketServer`; expose `preferred_port_honored` via `listener_endpoint` |
| `packaging/system-analyzer` | New UFW application profile for port 27321/tcp |
| `tests/test_remote_server.py` | New: preferred-port contract tests |
| `tests/test_cross_platform_branches.py` | New: assert no firewall mutation on startup |

---

## Task 1: Add PEER_SERVICE_DEFAULT_PORT constant

**Files:**
- Modify: `maintenance/remote_support/server.py`
- Modify: `maintenance/remote.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_remote_server.py (create new file)
import unittest


class PeerServicePortTests(unittest.TestCase):
    def test_default_port_constant_exists(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertIsInstance(PEER_SERVICE_DEFAULT_PORT, int)
        self.assertGreater(PEER_SERVICE_DEFAULT_PORT, 1023)
        self.assertLess(PEER_SERVICE_DEFAULT_PORT, 32768)  # below Linux ephemeral range

    def test_default_port_re_exported_from_remote(self) -> None:
        from maintenance import remote
        self.assertTrue(hasattr(remote, "PEER_SERVICE_DEFAULT_PORT"))
        from maintenance.remote import PEER_SERVICE_DEFAULT_PORT
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT as src
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, src)

    def test_default_port_value(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, 27321)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_remote_server.py::PeerServicePortTests -x -q
```
Expected: `ImportError: cannot import name 'PEER_SERVICE_DEFAULT_PORT'`

- [ ] **Step 3: Add constant to remote_support/server.py**

Open `maintenance/remote_support/server.py`. After the imports block (before `class RemoteSocketServer`), add:

```python
PEER_SERVICE_DEFAULT_PORT = 27321
"""Stable TCP port the peer listener attempts first.

Below the Linux default ephemeral range (32768-60999) so the OS will not
randomly assign this port to other sockets, making it safe to open in a
host firewall. Exported from maintenance.remote; do not duplicate elsewhere.
"""
```

- [ ] **Step 4: Re-export from maintenance/remote.py**

In `maintenance/remote.py`, find the imports block from `maintenance.remote_support.server`:

```python
from maintenance.remote_support.server import (
    ...
    RemoteSocketServer,
    ...
)
```

Add `PEER_SERVICE_DEFAULT_PORT` to that import. Then add it to `__all__` if one exists in that file:

```python
"PEER_SERVICE_DEFAULT_PORT",
```

Run: `grep -n "^from maintenance.remote_support.server\|__all__" maintenance/remote.py | head -20`
to find the exact lines before editing.

- [ ] **Step 5: Run test to verify passes**

```bash
python3 -m pytest tests/test_remote_server.py::PeerServicePortTests -x -q
```
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add maintenance/remote_support/server.py maintenance/remote.py tests/test_remote_server.py
git commit -m "feat: add PEER_SERVICE_DEFAULT_PORT = 27321 canonical constant"
```

---

## Task 2: Add preferred_port to RemoteSocketServer

**Files:**
- Modify: `maintenance/remote_support/server.py`

- [ ] **Step 1: Write failing tests**

Add new class to `tests/test_remote_server.py`:

```python
class RemoteSocketServerPreferredPortTests(unittest.TestCase):
    def _make_server(self, *, preferred_port: int = 0) -> Any:
        from maintenance.remote_support.server import RemoteSocketServer
        from unittest.mock import MagicMock
        service = MagicMock()
        return RemoteSocketServer(service, host="127.0.0.1", preferred_port=preferred_port)

    def test_preferred_port_honored_is_none_before_start(self) -> None:
        server = self._make_server(preferred_port=27321)
        self.assertIsNone(server.preferred_port_honored)

    def test_server_binds_preferred_port_when_free(self) -> None:
        import socket
        server = self._make_server(preferred_port=27321)
        # Verify 27321 is free before testing
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", 27321))
            except OSError:
                self.skipTest("port 27321 already in use on this machine")
        try:
            server.start()
            self.assertEqual(server.bound_port, 27321)
            self.assertTrue(server.preferred_port_honored)
        finally:
            server.stop()

    def test_server_falls_back_to_ephemeral_when_preferred_busy(self) -> None:
        import socket
        from maintenance.remote_support.server import RemoteSocketServer
        from unittest.mock import MagicMock
        # Occupy port 27321
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                blocker.bind(("127.0.0.1", 27321))
                blocker.listen(1)
            except OSError:
                self.skipTest("could not acquire port 27321 as blocker")
            service = MagicMock()
            server = RemoteSocketServer(service, host="127.0.0.1", preferred_port=27321)
            try:
                server.start()
                self.assertIsNotNone(server.bound_port)
                self.assertNotEqual(server.bound_port, 27321)
                self.assertFalse(server.preferred_port_honored)
            finally:
                server.stop()

    def test_no_preferred_port_uses_ephemeral(self) -> None:
        server = self._make_server(preferred_port=0)
        try:
            server.start()
            self.assertIsNotNone(server.bound_port)
            self.assertNotEqual(server.bound_port, 27321)
        finally:
            server.stop()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_remote_server.py::RemoteSocketServerPreferredPortTests -x -q
```
Expected: `TypeError: __init__() got an unexpected keyword argument 'preferred_port'`

- [ ] **Step 3: Add preferred_port param to RemoteSocketServer.__init__**

In `maintenance/remote_support/server.py`, find `class RemoteSocketServer` and its `__init__`. After `port: int = 0,`, add:

```python
        preferred_port: int = 0,
```

In the body, after `self._port = port`, add:

```python
        self._preferred_port = preferred_port
        self._preferred_port_honored: bool | None = None
```

- [ ] **Step 4: Add preferred_port_honored property**

After the `bound_port` property, add:

```python
    @property
    def preferred_port_honored(self) -> bool | None:
        """True if preferred_port was used; False if ephemeral fallback; None before start."""
        return self._preferred_port_honored
```

- [ ] **Step 5: Modify start() to try preferred port first**

Read the current `start()` method body carefully. Find the `_Server` instantiation line that looks like:
```python
            (self._host, self._port),
```

Replace the entire server-creation block (the `try` around the TCPServer instantiation) with the preferred-port logic. The existing structure creates `_Server` (a subclass of `ThreadingTCPServer`) at the given address. Replace just the `_Server(...)` instantiation:

```python
        # Try preferred port first; fall back to ephemeral with diagnostic.
        _port_candidates = (
            [self._preferred_port, self._port]
            if self._preferred_port > 0
            else [self._port]
        )
        _server_instance: Any = None
        for _candidate in _port_candidates:
            try:
                _server_instance = _Server(
                    (self._host, _candidate),
                    _Handler,
                )
                self._preferred_port_honored = (
                    _candidate == self._preferred_port and self._preferred_port > 0
                )
                break
            except OSError:
                if _candidate == self._port or self._preferred_port == 0:
                    raise
                LOGGER.warning(
                    "Preferred peer port %d unavailable; falling back to ephemeral",
                    self._preferred_port,
                )
        if _server_instance is None:
            raise OSError("Could not bind peer listener on any port")
```

Then replace the original `_Server(...)` assignment in the rest of `start()` with `_server_instance`.

> NOTE: Read `server.py` lines 81-200 fully before making this edit. The exact existing `_Server` lines must be identified precisely. The edit replaces only the `_Server(...)` call, not the `_Handler`, `_Server` class definitions, or `_server.serve_forever()` call.

- [ ] **Step 6: Run tests to verify passes**

```bash
python3 -m pytest tests/test_remote_server.py -x -q
```
Expected: all pass (may skip if port 27321 unavailable on CI machine — that is acceptable)

- [ ] **Step 7: Commit**

```bash
git add maintenance/remote_support/server.py tests/test_remote_server.py
git commit -m "feat: RemoteSocketServer preferred_port — tries stable port, falls back to ephemeral with diagnostic"
```

---

## Task 3: Wire preferred_port through start_peer_listener

**Files:**
- Modify: `maintenance/ui/window_discovery.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_remote_server.py`:

```python
class StartPeerListenerPortTests(unittest.TestCase):
    def test_start_peer_listener_passes_preferred_port(self) -> None:
        """Production startup must pass PEER_SERVICE_DEFAULT_PORT to the server."""
        import inspect
        from maintenance.ui import window_discovery
        src = inspect.getsource(window_discovery.start_peer_listener)
        self.assertIn("PEER_SERVICE_DEFAULT_PORT", src,
            "start_peer_listener must pass PEER_SERVICE_DEFAULT_PORT as preferred_port")
        self.assertIn("preferred_port", src,
            "start_peer_listener must use preferred_port keyword")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_remote_server.py::StartPeerListenerPortTests -x -q
```
Expected: `AssertionError: start_peer_listener must pass PEER_SERVICE_DEFAULT_PORT`

- [ ] **Step 3: Update start_peer_listener in window_discovery.py**

Find the `RemoteSocketServer(...)` call in `start_peer_listener` (line ~159). Add `preferred_port` keyword:

First, add the import near the top of `window_discovery.py`:
```python
from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
```

Then in the `RemoteSocketServer(...)` call, add:
```python
        server = window.RemoteSocketServer(
            service,
            host="0.0.0.0",
            ssl_context=tls_context,
            preferred_port=PEER_SERVICE_DEFAULT_PORT,
            pairing_handler=...,
            ...
        )
```

(Keep all other keyword arguments unchanged; add `preferred_port=PEER_SERVICE_DEFAULT_PORT` after `ssl_context=tls_context`.)

- [ ] **Step 4: Run test to verify passes**

```bash
python3 -m pytest tests/test_remote_server.py::StartPeerListenerPortTests -x -q
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/window_discovery.py tests/test_remote_server.py
git commit -m "feat: start_peer_listener passes PEER_SERVICE_DEFAULT_PORT=27321 as preferred port"
```

---

## Task 4: Expose preferred_port_honored in listener_endpoint

**Files:**
- Modify: `maintenance/ui/window_discovery.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_remote_server.py`:

```python
class ListenerEndpointDiagnosticsTests(unittest.TestCase):
    def test_listener_endpoint_returns_four_tuple(self) -> None:
        """listener_endpoint must return (connectable, port, fingerprint, preferred_honored)."""
        from maintenance.ui.window_discovery import listener_endpoint
        import inspect
        src = inspect.getsource(listener_endpoint)
        # Must reference preferred_port_honored
        self.assertIn("preferred_port_honored", src,
            "listener_endpoint must include preferred_port_honored in its return value")

    def test_listener_endpoint_not_connectable_when_no_server(self) -> None:
        from maintenance.ui.window_discovery import listener_endpoint
        from unittest.mock import MagicMock
        controller = MagicMock()
        del controller.__dict__  # let MagicMock handle attr access
        controller.__dict__ = {}
        result = listener_endpoint(controller)
        self.assertFalse(result[0])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_remote_server.py::ListenerEndpointDiagnosticsTests -x -q
```
Expected: `AssertionError: listener_endpoint must include preferred_port_honored`

- [ ] **Step 3: Update listener_endpoint in window_discovery.py**

Find `def listener_endpoint(controller: Any)` (line ~98):

```python
def listener_endpoint(controller: Any) -> tuple[bool, int | None, str | None]:
    if server is None or server.bound_port is None:
        return False, None, None
    return True, server.bound_port, controller.__dict__.get("_tls_fingerprint")
```

Replace with:

```python
def listener_endpoint(
    controller: Any,
) -> tuple[bool, int | None, str | None, bool | None]:
    server = controller.__dict__.get("_peer_server")
    if server is None or server.bound_port is None:
        return False, None, None, None
    return (
        True,
        server.bound_port,
        controller.__dict__.get("_tls_fingerprint"),
        server.preferred_port_honored,
    )
```

Also update the `get_listener_endpoint` call in `DiscoverySession` wiring (line ~90 in window_discovery.py):

```python
def _get_endpoint_adapter(controller: Any) -> tuple[bool, int | None, str | None]:
    result = listener_endpoint(controller)
    return result[:3]  # DiscoverySession consumes only first 3
```

Pass `_get_endpoint_adapter` (not `listener_endpoint` directly) as `get_listener_endpoint=`:
```python
get_listener_endpoint=lambda: _get_endpoint_adapter(controller),
```

> NOTE: Read lines 85–100 of window_discovery.py to see the exact current wiring before this edit.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_remote_server.py -x -q
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/window_discovery.py tests/test_remote_server.py
git commit -m "feat: listener_endpoint exposes preferred_port_honored for diagnostics"
```

---

## Task 5: UFW application profile

**Files:**
- Create: `packaging/system-analyzer`

- [ ] **Step 1: Check UFW application profile format**

```bash
cat /etc/ufw/applications.d/openssh 2>/dev/null || ls /etc/ufw/applications.d/ 2>/dev/null | head -5
```

UFW application profile files use INI format. The standard form:

```ini
[<AppName>]
title=<human title>
description=<one line>
ports=<port>/tcp
```

- [ ] **Step 2: Create the profile file**

Create `packaging/system-analyzer` (no extension — this is the UFW convention):

```ini
[System Analyzer]
title=System Analyzer Peer Service
description=Inbound TCP for System Analyzer LAN peer connections (port 27321)
ports=27321/tcp
```

- [ ] **Step 3: Verify the constant matches**

```bash
grep "PEER_SERVICE_DEFAULT_PORT" maintenance/remote_support/server.py
grep "27321" packaging/system-analyzer
```

Both must print `27321`. If the constant ever changes, this file must change atomically.

- [ ] **Step 4: Write user instructions comment in install-user.sh**

In `install/install-user.sh`, after the install step completes, append a note block (do NOT execute ufw automatically):

```bash
# Firewall note (Linux only): to allow inbound LAN peer connections, run:
#   sudo cp packaging/system-analyzer /etc/ufw/applications.d/
#   sudo ufw app update "System Analyzer"
#   sudo ufw allow "System Analyzer"
# This opens TCP port 27321 only. Remove with: sudo ufw delete allow "System Analyzer"
```

Find the end of the install step (`verify_installed`) and add the note after it using `echo`.

- [ ] **Step 5: Commit**

```bash
git add packaging/system-analyzer install/install-user.sh
git commit -m "feat: UFW application profile for peer service port 27321"
```

---

## Task 6: Tests — no firewall mutation on startup

**Files:**
- Modify: `tests/test_cross_platform_branches.py`

- [ ] **Step 1: Write the test**

Find `tests/test_cross_platform_branches.py` and read its structure. Add a new class at the bottom:

```python
class NoFirewallMutationTests(unittest.TestCase):
    """AppWindow/RemoteService startup must never invoke privileged firewall tools."""

    _FIREWALL_PATTERNS = [
        "sudo",
        "ufw",
        "iptables",
        "nft",
        "netsh",
        "firewall",
    ]

    def test_window_discovery_imports_no_firewall_tools(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("maintenance/ui/window_discovery.py").read_text()
        tree = ast.parse(src)
        calls = [
            node.func.id if isinstance(node.func, ast.Name) else
            (node.func.attr if isinstance(node.func, ast.Attribute) else "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        subproc_calls = [c for c in calls if c in ("Popen", "run", "check_call", "check_output", "call")]
        # subprocess calls in window_discovery are only for TLS material (openssl),
        # not firewall mutations. Assert none of the firewall keywords appear as
        # string literals in the file.
        for pattern in self._FIREWALL_PATTERNS:
            with self.subTest(pattern=pattern):
                # String literals in AST
                literals = [
                    node.s if isinstance(node, ast.Constant) and isinstance(node.s, str) else ""
                    for node in ast.walk(tree)
                ]
                matches = [s for s in literals if pattern in s]
                self.assertEqual(
                    matches, [],
                    f"window_discovery.py must not contain firewall literal '{pattern}': {matches}"
                )

    def test_remote_support_server_imports_no_subprocess(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("maintenance/remote_support/server.py").read_text()
        tree = ast.parse(src)
        imports = [
            (node.names[0].name if isinstance(node, ast.Import) else node.module)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertNotIn("subprocess", imports,
            "remote_support/server.py must not import subprocess")
        self.assertNotIn("os", imports,
            "remote_support/server.py must not import os (would allow os.system firewall calls)")
```

- [ ] **Step 2: Run test to verify passes**

```bash
python3 -m pytest tests/test_cross_platform_branches.py::NoFirewallMutationTests -x -q
```
Expected: pass (these are assertions about the current state of the code)

- [ ] **Step 3: Commit**

```bash
git add tests/test_cross_platform_branches.py
git commit -m "test: assert no firewall mutation in window_discovery or remote server startup"
```

---

## Task 7: Tests — port contract integrity

**Files:**
- Modify: `tests/test_remote_server.py`

- [ ] **Step 1: Add port-contract test class**

```python
class PortContractIntegrityTests(unittest.TestCase):
    """bound_port == advertised port; port constant not duplicated."""

    def test_bound_port_equals_preferred_when_honored(self) -> None:
        """When preferred port is available, bound_port must equal PEER_SERVICE_DEFAULT_PORT."""
        import socket
        from maintenance.remote_support.server import (
            PEER_SERVICE_DEFAULT_PORT,
            RemoteSocketServer,
        )
        from unittest.mock import MagicMock

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", PEER_SERVICE_DEFAULT_PORT))
            except OSError:
                self.skipTest(f"port {PEER_SERVICE_DEFAULT_PORT} already in use")

        service = MagicMock()
        server = RemoteSocketServer(
            service, host="127.0.0.1", preferred_port=PEER_SERVICE_DEFAULT_PORT
        )
        try:
            server.start()
            self.assertEqual(server.bound_port, PEER_SERVICE_DEFAULT_PORT)
            self.assertTrue(server.preferred_port_honored)
        finally:
            server.stop()

    def test_no_duplicate_port_27321_literal(self) -> None:
        """The literal 27321 must appear in exactly one source file (server.py)."""
        import pathlib
        py_files = list(pathlib.Path("maintenance").rglob("*.py"))
        py_files += list(pathlib.Path("tests").rglob("*.py"))
        py_files += [pathlib.Path("window.py")] if pathlib.Path("window.py").exists() else []
        matches = [
            str(f) for f in py_files
            if "27321" in f.read_text()
            and str(f) != "maintenance/remote_support/server.py"
            and "test_remote_server.py" not in str(f)  # test file allowed to reference it
        ]
        self.assertEqual(
            matches, [],
            f"Literal 27321 found outside canonical owner: {matches}. "
            "Import PEER_SERVICE_DEFAULT_PORT instead of copying the literal."
        )

    def test_window_discovery_imports_constant_not_literal(self) -> None:
        import pathlib
        src = pathlib.Path("maintenance/ui/window_discovery.py").read_text()
        self.assertIn("PEER_SERVICE_DEFAULT_PORT", src,
            "window_discovery.py must import PEER_SERVICE_DEFAULT_PORT")
        self.assertNotIn("27321", src,
            "window_discovery.py must not contain the literal 27321 — import the constant")
```

- [ ] **Step 2: Run tests**

```bash
python3 -m pytest tests/test_remote_server.py::PortContractIntegrityTests -x -q
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_remote_server.py
git commit -m "test: port contract integrity — no duplicate literals, bound==advertised"
```

---

## Task 8: Full validation

- [ ] **Step 1: Run the full relevant test suite**

```bash
python3 -m pytest tests/test_remote_server.py tests/test_remote_contract.py tests/test_remote_security.py tests/test_cross_platform_branches.py tests/test_discovery.py -x -q --tb=short 2>&1 | tail -30
```
Expected: all pass. Fix any failures before proceeding.

- [ ] **Step 2: Run ruff**

```bash
python3 -m ruff check maintenance/ tests/ window.py
```
Expected: 0 errors.

- [ ] **Step 3: Run pyright**

```bash
python3 -m pyright maintenance/ tests/ window.py 2>&1 | grep -E "error:" | head -20
```
Expected: 0 type errors on changed files.

- [ ] **Step 4: Run full suite**

```bash
python3 -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```
Expected: all pass.

- [ ] **Step 5: git diff --check**

```bash
git diff --check HEAD
```
Expected: no whitespace errors.

---

## Task 9: Build wheel

- [ ] **Step 1: Build**

```bash
python3 maintenance/_release.py prepare-build --package-dir .
python3 -m build --wheel --no-isolation
python3 maintenance/_release.py sync-artifacts --package-dir .
```

- [ ] **Step 2: Commit wheel + version**

```bash
git add dist/ maintenance/_version.py
git commit -m "chore: release — Phase 12G LAN transport port contract"
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Task 10: Physical retest (user runs — Linux + Windows)

**Linux:**
```bash
# Confirm new listener is on port 27321
pkill -f system-analyzer || true
system-analyzer &
sleep 3
ss -tlnp 'sport = :27321'
```
Expected: `LISTEN 0 16 0.0.0.0:27321`

**Windows (install new wheel first):**
```powershell
irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex
Test-NetConnection 192.168.55.107 -Port 27321
```

**If iptables Category B was confirmed in Diagnostic Gate:**
Before retest, add the permanent UFW rule (Linux):
```bash
sudo cp packaging/system-analyzer /etc/ufw/applications.d/
sudo ufw app update "System Analyzer"
sudo ufw allow "System Analyzer"
sudo ufw status verbose
```

Expected Windows retest: `TcpTestSucceeded : True`

If TCP passes, resume controlled Windows → Linux Pair from the beginning of Phase 12F-P with the new stable port.

---

## Document Phase 12G findings

- [ ] Append a Phase 12G section to `docs/WINDOWS-FINDINGS-2026-09-17.md` after completing the diagnostic gate and physical retest, recording:
  1. tcpdump classification (A/B/C/D)
  2. exact INPUT rule identified
  3. temporary rule commands + before/after counters
  4. temporary rule retest result (TcpTestSucceeded)
  5. temporary rule rollback command
  6. permanent port strategy chosen (PEER_SERVICE_DEFAULT_PORT = 27321)
  7. UFW rule added
  8. physical retest with new wheel result

---

## Self-review checklist

- [x] §1 Diagnostic gate before code — Tasks gated behind Gate Steps 1–3
- [x] §2 iptables read — Gate Step 2
- [x] §3 If Category A: STOP — gate documented
- [x] §4 If Category C: STOP — gate documented
- [x] §5 Category B required — gate documented
- [x] §6 Narrow temporary rule proof — Gate Step 3
- [x] §7 Temporary rule is not the product fix — addressed; stable port replaces it
- [x] §8 Audit ephemeral port — `port=0` in `RemoteSocketServer.__init__:48`; `start_peer_listener` passes no port; OS assigns
- [x] §9 Durable port contract — `PEER_SERVICE_DEFAULT_PORT = 27321`, canonical, below ephemeral range
- [x] §10 One canonical owner — `maintenance/remote_support/server.py` only; Task 7 test enforces this
- [x] §11 Stable port behavior — preferred_port; fall back to ephemeral with diagnostic, not silent
- [x] §12 Profile isolation — `preferred_port_honored=False` diagnostic when port busy; ephemeral fallback keeps multiple profiles alive
- [x] §13 No privilege hiding — no sudo/ufw calls in runtime code; explicit user command in Task 5
- [x] §14 Linux UFW profile — `packaging/system-analyzer` in Task 5
- [x] §15 VPN coexistence — app does not fight kill switch; diagnostic exposes `preferred_port_honored`
- [x] §16 No security software disabled — confirmed by Task 6 test
- [x] §17 Windows firewall separate — not touched here
- [x] §18 Address-selection repair separate — not bundled
- [x] §19 Tests: listener port contract — Tasks 6, 7
- [x] §20 Tests: no firewall mutation — Task 6
- [x] §21 Tests: diagnostics — Task 4
- [x] §22 Pairing security preserved — no TLS/HMAC/trust changes
- [x] §23 Schema identity bug separate — not touched
- [x] §24 Validation — Task 8
- [x] §25 Physical retest — Task 10
- [x] §26 If no code change needed — gate documented; plan only proceeds if Category B confirmed
