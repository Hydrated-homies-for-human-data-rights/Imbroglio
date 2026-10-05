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
private at connect time) is not prevented. Acceptable for a
password-protected prototype; the production pipeline should pin resolved
addresses or egress through a filtering proxy.
"""

from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlparse


class BlockedURL(Exception):
    """Raised when a URL targets a disallowed scheme or address."""


@lru_cache(maxsize=4096)
def _host_allowed(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # unresolvable: the fetch fails on its own, nothing to protect
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
    if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        raise BlockedURL(f"internal hostname: {host}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise BlockedURL(f"IP address literals not allowed: {host}")
    if not _host_allowed(host):
        raise BlockedURL(f"resolves to a non-public address: {host}")


def is_allowed(url: str) -> bool:
    try:
        check_url(url)
        return True
    except BlockedURL:
        return False
