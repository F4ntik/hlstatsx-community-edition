"""Database-backed hostname resolution for ``hlstats-resolve``."""

from __future__ import annotations

import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Callable, Sequence, TYPE_CHECKING

from proxy_daemon_py.db import (
    DatabaseConfig as DaemonDatabaseConfig,
    SupportsConnection,
    SyncDatabaseAdapter,
)

if TYPE_CHECKING:  # pragma: no cover - used for static analysis only
    from .cli import DatabaseConfig as CliDatabaseConfig
    from .cli import RuntimeSettings

_LOGGER = logging.getLogger(__name__)

_HOSTGROUP_QUERY = (
    "SELECT pattern, name FROM hlstats_HostGroups ORDER BY LENGTH(pattern) DESC, pattern ASC"
)
_REGROUP_QUERY = (
    "SELECT id, hostname FROM hlstats_Events_Connects WHERE hostname IS NOT NULL AND hostname != ''"
)
_RESOLVE_QUERY = (
    "SELECT DISTINCT ipAddress, hostname FROM hlstats_Events_Connects"
)
_UPDATE_REGROUP = "UPDATE hlstats_Events_Connects SET hostgroup = %s WHERE id = %s"
_UPDATE_RESOLVE = (
    "UPDATE hlstats_Events_Connects SET hostname = %s, hostgroup = %s WHERE ipAddress = %s"
)

_DOM_NO_SLD = (
    "ca",
    "ch",
    "be",
    "de",
    "ee",
    "es",
    "fi",
    "fr",
    "ie",
    "nl",
    "no",
    "ru",
    "se",
)


class ResolveError(RuntimeError):
    """Raised when the resolver encounters unrecoverable input data."""


@dataclass(frozen=True, slots=True)
class ResolveSummary:
    """Aggregate information about a resolver run."""

    total_connects: int
    resolved_ips: int
    regrouped_hosts: int


@dataclass(frozen=True, slots=True)
class _HostGroupRule:
    pattern: str
    name: str
    regex: re.Pattern[str]

    def matches(self, hostname: str) -> bool:
        return bool(self.regex.search(hostname))


class HostResolver:
    """Mirror the behaviour of ``hlstats-resolve.pl`` using ``SyncDatabaseAdapter``."""

    def __init__(
        self,
        adapter: SyncDatabaseAdapter,
        *,
        dns_timeout: int,
        debug_level: int,
        resolver: Callable[[str, float], str] | None = None,
    ) -> None:
        if dns_timeout <= 0:
            raise ValueError("dns_timeout must be positive")
        self._adapter = adapter
        self._dns_timeout = float(dns_timeout)
        self._debug_level = debug_level
        self._resolver_override = resolver

    def run(self, *, regroup_only: bool) -> ResolveSummary:
        """Execute the resolver and return a summary of the work performed."""

        if self._resolver_override is None:
            with ThreadPoolExecutor(max_workers=4) as executor:
                return self._execute(regroup_only, lambda ip: self._resolve_with_executor(executor, ip))
        return self._execute(
            regroup_only,
            lambda ip: self._resolver_override(ip, self._dns_timeout),
        )

    # ------------------------------------------------------------------
    # Internal helpers

    def _execute(self, regroup_only: bool, resolver: Callable[[str], str]) -> ResolveSummary:
        connection = self._adapter.connection()
        rules = self._load_hostgroups(connection)

        if regroup_only:
            rows = self._fetch_all(connection, _REGROUP_QUERY)
            total = 0
            for connect_id, hostname in rows:
                total += 1
                host_text = self._clean_hostname(hostname)
                hostgroup = self._determine_hostgroup(host_text, rules)
                self._execute_update(connection, _UPDATE_REGROUP, (hostgroup, connect_id))
                self._log_progress("regroup", host_text, hostgroup)
            return ResolveSummary(total_connects=total, resolved_ips=0, regrouped_hosts=total)

        rows = self._fetch_all(connection, _RESOLVE_QUERY)
        total = 0
        resolved_ips = 0
        for ip_address, hostname in rows:
            total += 1
            ip_text = self._clean_ip(ip_address)
            existing_hostname = self._clean_hostname(hostname)

            if existing_hostname:
                resolved_name = existing_hostname
                was_resolved = False
            else:
                resolved_name = resolver(ip_text).strip().lower()
                was_resolved = bool(resolved_name)

            hostgroup = self._determine_hostgroup(resolved_name, rules) if resolved_name else ""
            self._execute_update(
                connection,
                _UPDATE_RESOLVE,
                (resolved_name, hostgroup, ip_text),
            )
            if was_resolved:
                resolved_ips += 1
            self._log_progress("resolve", resolved_name or existing_hostname, hostgroup, ip_text)

        return ResolveSummary(total_connects=total, resolved_ips=resolved_ips, regrouped_hosts=total)

    def _load_hostgroups(self, connection: SupportsConnection) -> list[_HostGroupRule]:
        rows = self._fetch_all(connection, _HOSTGROUP_QUERY)
        rules: list[_HostGroupRule] = []
        for pattern, name in rows:
            pattern_text = self._clean_pattern(pattern)
            if not pattern_text:
                raise ResolveError("Host group pattern cannot be empty")
            regex = self._compile_pattern(pattern_text)
            rules.append(_HostGroupRule(pattern=pattern_text, name=str(name), regex=regex))
        return rules

    def _resolve_with_executor(self, executor: ThreadPoolExecutor, ip_address: str) -> str:
        future = executor.submit(socket.gethostbyaddr, ip_address)
        try:
            host, _aliases, _addresses = future.result(timeout=self._dns_timeout)
        except FuturesTimeoutError:
            future.cancel()
            _LOGGER.warning("DNS lookup timed out for %s after %.1f seconds", ip_address, self._dns_timeout)
            return ""
        except socket.herror:
            return ""
        except OSError as exc:
            _LOGGER.debug("DNS lookup failed for %s: %s", ip_address, exc)
            return ""
        return str(host).strip().lower()

    def _determine_hostgroup(self, hostname: str, rules: Sequence[_HostGroupRule]) -> str:
        if not hostname:
            return ""

        normalized = hostname.lower()
        for rule in rules:
            if rule.matches(normalized):
                return rule.name

        dom_pattern = "|".join(_DOM_NO_SLD)
        match = re.search(rf"([\w-]+\.(?:{dom_pattern}|\w{{3,}}))$", normalized)
        if match:
            return match.group(1)

        match = re.search(r"([\w-]+\.[\w-]+\.\w\w)$", normalized)
        if match:
            return match.group(1)

        return normalized

    def _compile_pattern(self, pattern: str) -> re.Pattern[str]:
        escaped = re.escape(pattern)
        wildcarded = escaped.replace(r"\*", "[^.]*")
        return re.compile(rf"{wildcarded}$")

    def _fetch_all(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[object] | None = None,
    ) -> list[tuple[object, ...]]:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def _execute_update(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[object],
    ) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute(query, params)
        finally:
            cursor.close()

    def _clean_hostname(self, hostname: object | None) -> str:
        if hostname is None:
            return ""
        text = str(hostname).strip()
        return text

    def _clean_ip(self, ip_address: object | None) -> str:
        if ip_address is None:
            raise ResolveError("Connect record is missing an IP address")
        text = str(ip_address).strip()
        if not text:
            raise ResolveError("Connect record has an empty IP address")
        return text

    def _clean_pattern(self, pattern: object | None) -> str:
        if pattern is None:
            return ""
        return str(pattern).strip().lower()

    def _log_progress(
        self,
        mode: str,
        hostname: str,
        hostgroup: str,
        ip_address: str | None = None,
    ) -> None:
        if self._debug_level <= 0:
            return
        if mode == "regroup":
            _LOGGER.info("host %s grouped as %s", hostname or "<unknown>", hostgroup or "<none>")
        else:
            _LOGGER.info(
                "ip %s resolved to %s grouped as %s",
                ip_address or "<unknown>",
                hostname or "<unresolved>",
                hostgroup or "<none>",
            )


def build_database_config(settings: RuntimeSettings) -> DaemonDatabaseConfig:
    """Translate CLI/runtime settings into a proxy-daemon DB configuration."""

    db_settings: CliDatabaseConfig = settings.database
    host = db_settings.host.strip()
    port = 3306
    if ":" in host:
        host, port_text = host.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ResolveError(f"Invalid port in database host specification: {db_settings.host!r}") from exc
    if not host:
        raise ResolveError("Database host must be provided")

    return DaemonDatabaseConfig(
        host=host,
        port=port,
        username=db_settings.username,
        password=db_settings.password,
        database=db_settings.name,
    )


__all__ = [
    "HostResolver",
    "ResolveError",
    "ResolveSummary",
    "build_database_config",
]
