from __future__ import annotations

from hlstats_resolve_py.resolver import HostResolver, ResolveSummary
from hlstats_resolve_py.tests.util import InMemoryConnection, StubAdapter


def test_regroup_only_updates_hostgroups() -> None:
    connection = InMemoryConnection(
        hostgroups=[("*.example.com", "Example Inc"), ("*.trusted.net", "Trusted Networks")],
        regroup_rows=[
            (1, "Foo.Example.com"),
            (2, "vpn.trusted.net"),
            (3, "unknown.local"),
        ],
    )
    adapter = StubAdapter(connection)
    resolver = HostResolver(adapter, dns_timeout=5, debug_level=1)

    summary = resolver.run(regroup_only=True)

    assert summary == ResolveSummary(total_connects=3, resolved_ips=0, regrouped_hosts=3)
    assert connection.regroup_updates == [
        ("Example Inc", 1),
        ("Trusted Networks", 2),
        ("unknown.local", 3),
    ]


def test_resolve_updates_missing_hostnames() -> None:
    connection = InMemoryConnection(
        hostgroups=[("*.isp.net", "ISP Net")],
        resolve_rows=[
            ("203.0.113.1", ""),
            ("203.0.113.2", "existing.example.com"),
        ],
    )
    adapter = StubAdapter(connection)

    def fake_resolver(ip: str, _timeout: float) -> str:
        return {"203.0.113.1": "User1.ISP.NET"}.get(ip, "")

    resolver = HostResolver(adapter, dns_timeout=5, debug_level=1, resolver=fake_resolver)

    summary = resolver.run(regroup_only=False)

    assert summary == ResolveSummary(total_connects=2, resolved_ips=1, regrouped_hosts=2)
    assert connection.resolve_updates == [
        ("user1.isp.net", "ISP Net", "203.0.113.1"),
        ("existing.example.com", "example.com", "203.0.113.2"),
    ]
