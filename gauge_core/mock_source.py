"""MockDataSource — drives gauges from the test harness over a local UDP socket.

The test harness sends packets of the form:
    {"sim/cockpit2/gauges/.../airspeed_kts_pilot": 120.0, ...}

This source listens on a configurable local port (default 49099), updates its
internal dict on each packet, and returns the current value for any dataref.
Datarefs not yet set by the harness return 0.0.

Used by the runner when launched with --mock.
"""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

DEFAULT_MOCK_PORT = 49099


class MockDataSource:
    def __init__(self, port: int = DEFAULT_MOCK_PORT) -> None:
        self._port = port
        self._values: dict[str, float] = {}
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def __call__(self, dataref: Any) -> float:
        key = dataref if isinstance(dataref, str) else str(dataref)
        with self._lock:
            return self._values.get(key, 0.0)

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self._port))
        self._sock.settimeout(0.1)
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        while self._running:
            try:
                data, _ = self._sock.recvfrom(65535)
                updates = json.loads(data.decode("utf-8"))
                if isinstance(updates, dict):
                    with self._lock:
                        self._values.update(
                            {k: float(v) for k, v in updates.items()}
                        )
            except socket.timeout:
                continue
            except Exception:
                continue

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
