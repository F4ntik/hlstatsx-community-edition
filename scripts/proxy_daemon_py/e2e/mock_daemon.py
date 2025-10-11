"""Simple UDP responder that emulates a downstream proxy daemon."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

_HEARTBEAT_PAYLOAD = b"C;HEARTBEAT;"
_HEARTBEAT_RESPONSE = b"Heartbeat OK"


@dataclass(slots=True)
class MockDaemonConfig:
    """Configuration for :func:`main`."""

    host: str
    port: int
    heartbeat_response: bytes = _HEARTBEAT_RESPONSE


class MockDaemonProtocol(asyncio.DatagramProtocol):
    """Respond to heartbeat messages and log forwarded traffic."""

    def __init__(self, config: MockDaemonConfig) -> None:
        self._config = config
        self._transport: asyncio.DatagramTransport | None = None
        self._log = logging.getLogger("mock-daemon")

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # pragma: no cover - integration
        self._transport = transport
        address = transport.get_extra_info("sockname")
        self._log.info("listening on %s", address)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        message = data.decode("utf-8", errors="replace").strip()
        self._log.info("received %r from %s:%s", message, addr[0], addr[1])
        if data.strip() == _HEARTBEAT_PAYLOAD:
            self._respond(self._config.heartbeat_response, addr)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - logging only
        self._log.error("datagram error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover - logging only
        if exc is not None:
            self._log.error("connection closed: %s", exc)
        else:
            self._log.info("connection closed")

    def _respond(self, payload: bytes, addr: tuple[str, int]) -> None:
        if self._transport is None:
            self._log.warning("transport not ready to respond")
            return
        self._transport.sendto(payload, addr)


async def _serve(config: MockDaemonConfig) -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: MockDaemonProtocol(config),
        local_addr=(config.host, config.port),
    )
    try:
        await asyncio.Event().wait()
    finally:
        transport.close()
        await asyncio.sleep(0)


def _load_config() -> MockDaemonConfig:
    host = os.getenv("MOCK_DAEMON_HOST", "0.0.0.0")
    port = int(os.getenv("MOCK_DAEMON_PORT", "27900"))
    response = os.getenv("MOCK_DAEMON_HEARTBEAT_RESPONSE", "Heartbeat OK").encode("utf-8")
    return MockDaemonConfig(host=host, port=port, heartbeat_response=response)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
    config = _load_config()
    asyncio.run(_serve(config))


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    main()
