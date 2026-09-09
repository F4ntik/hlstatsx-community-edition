from __future__ import annotations

import asyncio
import pytest
import socket
from io import StringIO

from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import InboundDatagram, ProxyUdpServer


def test_udp_server_enqueues_valid_datagram() -> None:
    asyncio.run(_run_enqueues_valid_datagram())


def test_udp_server_drops_invalid_payloads() -> None:
    asyncio.run(_run_drops_invalid_payloads())


def test_udp_server_stop_receiving_keeps_outbound_transport_until_close() -> None:
    asyncio.run(_run_stop_receiving_keeps_outbound_transport_until_close())


async def _run_enqueues_valid_datagram() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    server = ProxyUdpServer(logger)
    await server.start("127.0.0.1", 0)

    address = server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        payload = b"PROXY Key=proxy-secret"
        sock.sendto(payload, address)

        datagram: InboundDatagram = await asyncio.wait_for(server.queue.get(), timeout=1)
    finally:
        sock.close()
        await server.stop()

    assert datagram.data == payload
    assert datagram.text == payload.decode("utf-8")
    assert datagram.address[0] == address[0]
    log_contents = buffer.getvalue()
    assert "Received" in log_contents
    assert "PROXY Key=<redacted>" in log_contents
    assert "proxy-secret" not in log_contents


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


async def _run_stop_receiving_keeps_outbound_transport_until_close() -> None:
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    await server.start("127.0.0.1", 0)
    address = server.address
    assert address is not None

    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1)
    try:
        await server.stop_receiving()
        receiver.sendto(b"inbound-after-quiesce", address)
        await asyncio.sleep(0)
        assert server.queue.empty()

        server.send_text("drained", receiver.getsockname())
        data, _ = await asyncio.wait_for(asyncio.to_thread(receiver.recvfrom, 1024), timeout=1)
    finally:
        receiver.close()
        await server.stop()

    assert data == b"drained"


def test_udp_server_start_twice_raises() -> None:
    asyncio.run(_run_start_twice_raises())

def test_udp_server_stop_without_start_is_safe() -> None:
    asyncio.run(_run_stop_without_start_is_safe())

def test_udp_server_send_text_requires_running() -> None:
    asyncio.run(_run_send_text_requires_running())

async def _run_start_twice_raises() -> None:
    server = ProxyUdpServer(ProxyLogger(LoggerConfig(stream=StringIO())))
    await server.start('127.0.0.1', 0)
    with pytest.raises(RuntimeError):
        await server.start('127.0.0.1', 0)
    await server.stop()

async def _run_stop_without_start_is_safe() -> None:
    server = ProxyUdpServer(ProxyLogger(LoggerConfig(stream=StringIO())))
    await server.stop()

async def _run_send_text_requires_running() -> None:
    server = ProxyUdpServer(ProxyLogger(LoggerConfig(stream=StringIO())))
    with pytest.raises(RuntimeError):
        server.send_text('payload', ('127.0.0.1', 9999))
