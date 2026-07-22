"""Asyncio UDP server utilities for the proxy daemon."""

from __future__ import annotations

import asyncio
import re
from asyncio import DatagramProtocol, DatagramTransport
from dataclasses import dataclass
from typing import Callable

from hlx_core.log import ProxyLogger


_PROXY_KEY_PATTERN = re.compile(r"(PROXY Key=)\S*")


def _redact_proxy_key(text: str) -> str:
    """Remove proxy key values from diagnostic output without altering packets."""

    return _PROXY_KEY_PATTERN.sub(r"\1<redacted>", text)


@dataclass(slots=True)
class InboundDatagram:
    """Container for UDP datagrams received by the proxy daemon."""

    data: bytes
    text: str
    address: tuple[str, int]


class ProxyDatagramProtocol(DatagramProtocol):
    """``asyncio`` protocol that forwards inbound datagrams to a queue."""

    def __init__(
        self,
        queue: asyncio.Queue[InboundDatagram],
        logger: ProxyLogger,
        *,
        max_packet_size: int = 4096,
    ) -> None:
        self._queue = queue
        self._logger = logger
        self._max_packet_size = max_packet_size
        self._transport: DatagramTransport | None = None

    def connection_made(self, transport: DatagramTransport) -> None:  # pragma: no cover - trivial
        self._transport = transport
        sockname = transport.get_extra_info("sockname")
        if sockname:
            host, port = sockname[:2]
            self._logger.daemon(f"UDP listener active on {host}:{port}")
        else:
            self._logger.daemon("UDP listener active")

    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover - trivial
        if exc is not None:
            self._logger.e403(f"UDP listener closed with error: {exc}")
        else:
            self._logger.daemon("UDP listener closed")
        self._transport = None

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - exercised implicitly
        self._logger.e403(f"UDP receive error: {exc}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        host, port = addr

        if not data:
            self._logger.control(f"Dropping empty datagram from {host}:{port}")
            return

        if len(data) > self._max_packet_size:
            self._logger.control(
                f"Dropping oversized datagram ({len(data)} bytes) from {host}:{port}"
            )
            return

        if b"\x00" in data:
            self._logger.control(f"Dropping datagram with NUL byte from {host}:{port}")
            return

        text = data.decode("utf-8", errors="replace")
        self._logger.control(
            f"Received {len(data)} bytes from {host}:{port}: {_redact_proxy_key(text)}",
        )
        self._queue.put_nowait(
            InboundDatagram(
                data=data,
                text=text,
                address=(host, port),
            )
        )


QueueFactory = Callable[[], asyncio.Queue[InboundDatagram]]


class ProxyUdpServer:
    """Thin wrapper around ``loop.create_datagram_endpoint``."""

    def __init__(self, logger: ProxyLogger, *, queue_factory: QueueFactory | None = None) -> None:
        self._logger = logger
        self._queue: asyncio.Queue[InboundDatagram]
        if queue_factory is not None:
            self._queue = queue_factory()
        else:
            self._queue = asyncio.Queue()
        self._transport: DatagramTransport | None = None
        self._protocol: ProxyDatagramProtocol | None = None
        self._listening_address: tuple[str, int] | None = None

    @property
    def queue(self) -> asyncio.Queue[InboundDatagram]:
        return self._queue

    @property
    def address(self) -> tuple[str, int] | None:
        """Return the bound address once the server has started."""

        return self._listening_address

    async def start(self, host: str | None, port: int) -> None:
        """Start listening for UDP packets on ``host``/``port``."""

        if self._transport is not None:
            raise RuntimeError("UDP server already running")

        loop = asyncio.get_running_loop()
        bind_host = host or "0.0.0.0"

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ProxyDatagramProtocol(self._queue, self._logger),
            local_addr=(bind_host, port),
        )
        self._transport = transport
        self._protocol = protocol
        sockname = transport.get_extra_info("sockname")
        if sockname:
            self._listening_address = (sockname[0], sockname[1])

    async def stop(self) -> None:
        """Stop listening for UDP packets."""

        if self._transport is None:
            return

        self._transport.close()
        self._transport = None
        self._protocol = None
        self._listening_address = None
        # Allow the event loop to process the close callback.
        await asyncio.sleep(0)

    def send_bytes(self, payload: bytes, address: tuple[str, int]) -> None:
        """Send ``payload`` to ``address`` using the underlying transport."""

        if self._transport is None:
            raise RuntimeError("UDP server is not running")
        self._transport.sendto(payload, address)

    def send_text(self, message: str, address: tuple[str, int]) -> None:
        """Encode *message* as UTF-8 and send it to ``address``."""

        self.send_bytes(message.encode("utf-8"), address)

