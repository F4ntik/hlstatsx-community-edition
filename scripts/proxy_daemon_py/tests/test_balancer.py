from __future__ import annotations

from datetime import datetime, timedelta, timezone

from proxy_daemon_py.balancer import Daemon, ServerBalancer


def _make_daemon(identifier: str, *, timeout: float = 30.0) -> Daemon:
    return Daemon(identifier=identifier, host="127.0.0.1", port=20000, heartbeat_timeout=timeout)


def test_round_robin_balancing_cycles_through_daemons() -> None:
    balancer = ServerBalancer()
    for index in range(3):
        balancer.register_daemon(_make_daemon(f"daemon-{index}"))

    assignments = [balancer.assign_server(f"10.0.0.{i}:27015") for i in range(6)]

    assert all(assignment is not None for assignment in assignments)
    assert [assignment.daemon_id for assignment in assignments if assignment is not None] == [
        "daemon-0",
        "daemon-1",
        "daemon-2",
        "daemon-0",
        "daemon-1",
        "daemon-2",
    ]


def test_assignment_is_sticky_while_daemon_is_available() -> None:
    balancer = ServerBalancer()
    balancer.register_daemon(_make_daemon("daemon-a"))
    balancer.register_daemon(_make_daemon("daemon-b"))

    first = balancer.assign_server("192.168.1.10:27015", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert first is not None

    reassigned = balancer.assign_server("192.168.1.10:27015", timestamp=datetime(2024, 1, 1, 0, 0, 5, tzinfo=timezone.utc))
    assert reassigned is first
    assert reassigned.assigned_at == datetime(2024, 1, 1, 0, 0, 5, tzinfo=timezone.utc)


def test_reassignment_when_daemon_marked_down() -> None:
    balancer = ServerBalancer()
    balancer.register_daemon(_make_daemon("daemon-a"))
    balancer.register_daemon(_make_daemon("daemon-b"))

    first = balancer.assign_server("example:27015", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert first is not None

    balancer.manager.mark_down(first.daemon_id)

    reassigned = balancer.assign_server("example:27015", timestamp=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc))
    assert reassigned is not None
    assert reassigned.daemon_id != first.daemon_id


def test_next_available_skips_daemons_with_expired_heartbeat() -> None:
    balancer = ServerBalancer()
    daemon_a = _make_daemon("daemon-a", timeout=5.0)
    daemon_b = _make_daemon("daemon-b")
    balancer.register_daemon(daemon_a)
    balancer.register_daemon(daemon_b)

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    balancer.manager.mark_heartbeat("daemon-a", timestamp=base_time)
    balancer.manager.mark_heartbeat("daemon-b", timestamp=base_time)

    first = balancer.assign_server("server-a:27015", timestamp=base_time)
    assert first is not None and first.daemon_id == "daemon-a"

    expired_time = base_time + timedelta(seconds=10)
    second = balancer.assign_server("server-b:27015", timestamp=expired_time)
    assert second is not None and second.daemon_id == "daemon-b"

    # Expired assignment should force reassignment even for sticky servers.
    third = balancer.assign_server("server-a:27015", timestamp=expired_time)
    assert third is not None and third.daemon_id == "daemon-b"

