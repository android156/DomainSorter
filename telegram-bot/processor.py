"""
processor.py — Business logic: parsing and sorting of domain/IP data.
All functions are pure (no DB calls) and fully decoupled.
"""

import ipaddress
import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns for .bat files
# ---------------------------------------------------------------------------

# IPv4 route: route ADD <ip4> MASK <mask4> 0.0.0.0 [...]
_IPV4_ROUTE = re.compile(
    r"^route\s+ADD\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3})"   # group 1 — IPv4 address
    r"\s+MASK\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3})"   # group 2 — subnet mask
    r"\s+0\.0\.0\.0\b.*$",
    re.IGNORECASE,
)

# IPv6 route: route ADD <ip6> MASK <anything> 0.0.0.0 [...]
_IPV6_ROUTE = re.compile(
    r"^route\s+ADD\s+"
    r"([0-9a-fA-F:]{2,39})"         # group 1 — IPv6 address
    r"\s+MASK\s+"
    r"([0-9a-fA-F:\.]+)"            # group 2 — mask (dotted or hex)
    r"\s+0\.0\.0\.0\b.*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Domain parsing
# ---------------------------------------------------------------------------

def parse_txt(content: str) -> list[str]:
    """
    Parse a plain-text file with domain names (one per line).

    - Strips whitespace
    - Ignores blank lines and lines starting with '#'
    - Lowercases each domain
    """
    domains: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            domains.append(line.lower())
    logger.info("parse_txt: found %d domain(s)", len(domains))
    return domains


# ---------------------------------------------------------------------------
# IP-route parsing
# ---------------------------------------------------------------------------

def _ip_sort_key(ip_str: str) -> bytes:
    """
    Return a sortable byte sequence for an IP address string.

    IPv4 addresses are prefixed with 0x00 (4+1 = 5 bytes total) so they
    sort before IPv6 addresses, which are prefixed with 0x01 (16+1 = 17 bytes).
    """
    try:
        return b"\x00" + ipaddress.IPv4Address(ip_str).packed
    except ValueError:
        pass
    try:
        return b"\x01" + ipaddress.IPv6Address(ip_str).packed
    except ValueError:
        pass
    # Fallback: compare lexicographically (should not happen with valid routes)
    return b"\xff" + ip_str.encode()


def parse_bat(content: str) -> list[dict]:
    """
    Parse a Windows .bat file that contains 'route ADD …' lines.

    Handles both IPv4 and IPv6 addresses.
    Preserves the exact original line format for output.

    Returns
    -------
    list of dicts with keys: ip, mask, original_line, sort_key (bytes)
    """
    routes: list[dict] = []
    skipped = 0

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        matched = False

        # Try IPv4 first
        m = _IPV4_ROUTE.match(stripped)
        if m:
            ip, mask = m.group(1), m.group(2)
            try:
                sort_key = _ip_sort_key(ip)
                routes.append(
                    {
                        "ip": ip,
                        "mask": mask,
                        "original_line": stripped,
                        "sort_key": sort_key,
                    }
                )
                matched = True
            except Exception as exc:
                logger.warning("IPv4 parse error for %r: %s", stripped, exc)

        if not matched:
            # Try IPv6
            m = _IPV6_ROUTE.match(stripped)
            if m:
                ip, mask = m.group(1), m.group(2)
                try:
                    sort_key = _ip_sort_key(ip)
                    routes.append(
                        {
                            "ip": ip,
                            "mask": mask,
                            "original_line": stripped,
                            "sort_key": sort_key,
                        }
                    )
                    matched = True
                except Exception as exc:
                    logger.warning("IPv6 parse error for %r: %s", stripped, exc)

        if not matched:
            skipped += 1
            logger.debug("Skipping non-route line: %r", stripped)

    logger.info(
        "parse_bat: found %d route(s), skipped %d line(s)", len(routes), skipped
    )
    return routes
