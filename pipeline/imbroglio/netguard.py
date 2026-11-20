"""Outbound request guard: refuse to fetch private, loopback, or cloud-internal
addresses (SSRF protection).

The pipeline fetches URLs it did not choose: whatever a user types, links
found on fetched pages, iframe sources, redirect targets, and every
subresource Chromium loads. Once deployed, any of those pointing at
169.254.169.254 (cloud metadata), 127.0.0.1, or the host's private network
would make our server read internal endpoints and show the result back.

Every fetch path calls check_url() before connecting:
  * fetch_static follows redirects manually so each hop is checked
  * fetch_rendered routes all browser requests through check_url

Known limit: DNS rebinding (a hostname resolving public at check time and
private at connect time) is narrowed, not prevented: a host's answer is
reused for at most HOST_TTL seconds, so a name that is re-pointed is checked
again within that time, but a quick enough switch between check and connect
still gets through. Pinning resolved addresses or a filtering egress proxy
would close it.

A refused host is reported as NO_PUBLIC_ADDRESS, the same words for a name
that resolves to a private address and for a name that doesn't resolve at
all, and without the name. These notes reach the public request log
(GET /v1/requests/{id}), and telling the two apart there would let anyone
map which internal names exist from where the worker runs.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse


class BlockedURL(Exception):
    """Raised when a URL targets a disallowed scheme or address."""


NO_PUBLIC_ADDRESS = "no public address"


HOST_TTL = 30.0  # seconds a host's check is reused (a page loads many resources)
_host_cache: dict[str, tuple[float, bool]] = {}
_host_lock = threading.Lock()


def _host_allowed(host: str) -> bool:
    now = time.monotonic()
    with _host_lock:
        hit = _host_cache.get(host)
    if hit is not None and now - hit[0] < HOST_TTL:
        return hit[1]
    ok = _resolve_allowed(host)
    with _host_lock:
        if len(_host_cache) > 4096:
            _host_cache.clear()
        _host_cache[host] = (now, ok)
    return ok


def clear_host_cache() -> None:
    with _host_lock:
        _host_cache.clear()


def _resolve_allowed(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Nothing to protect, but refused all the same so it reads exactly
        # like a private answer (see the module docstring).
        return False
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if not addr.is_global or addr.is_multicast:
            return False
    return True


def check_url(url: str) -> None:
    """Raise BlockedURL unless url is http(s) to a publicly routable host."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURL(f"scheme not allowed: {parsed.scheme or '(none)'}")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedURL("no host")
    try:
        host.encode("idna")
    except UnicodeError:
        # "www..usf.edu" or a 64+ character label: no such host can exist,
        # and the resolver raises UnicodeError, which ended usf.edu's whole
        # crawl (Nov 17) instead of skipping the one bad link.
        raise BlockedURL(f"not a valid host name: {host}") from None
    if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        raise BlockedURL(f"internal hostname: {host}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise BlockedURL(f"IP address literals not allowed: {host}")
    if not _host_allowed(host):
        raise BlockedURL(NO_PUBLIC_ADDRESS)


def is_allowed(url: str) -> bool:
    try:
        check_url(url)
        return True
    except BlockedURL:
        return False
