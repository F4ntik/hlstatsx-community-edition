from __future__ import annotations

import asyncio
import socket
from io import StringIO

from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import InboundDatagram, ProxyUdpServer


def test_udp_server_enqueues_valid_datagram() -> None:
    asyncio.run(_run_enqueues_valid_datagram())


def test_udp_server_drops_invalid_payloads() -> None:
    asyncio.run(_run_drops_invalid_payloads())


async def _run_enqueues_valid_datagram() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    server = ProxyUdpServer(logger)
    await server.start("127.0.0.1", 0)

    address = server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        payload = b"PROXY Key=test"
        sock.sendto(payload, address)

        datagram: InboundDatagram = await asyncio.wait_for(server.queue.get(), timeout=1)
    finally:
        sock.close()
        await server.stop()

    assert datagram.data == payload
    assert datagram.address[0] == address[0]
    assert "Received" in buffer.getvalue()


async def _run_drops_invalid_payloads() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    queue: asyncio.Queue[InboundDatagram] = asyncio.Queue()
    server = ProxyUdpServer(logger, queue_factory=lambda: queue)
    await server.start("127.0.0.1", 0)

    address = server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"\x00bad", address)
        await asyncio.sleep(0.1)
        assert queue.empty()
    finally:
        sock.close()
        await server.stop()

    log_contents = buffer.getvalue()
    assert "Dropping datagram with NUL byte" in log_contents
