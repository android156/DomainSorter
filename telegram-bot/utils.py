"""
utils.py — File splitting and formatting helpers.
All functions are pure; no I/O or DB dependencies.
"""

import logging

logger = logging.getLogger(__name__)


def _split_chunks(items: list[str], max_len: int) -> list[list[str]]:
    """Split a list into consecutive chunks of at most max_len elements."""
    return [items[i : i + max_len] for i in range(0, len(items), max_len)]


def make_domain_files(
    items: list[str], base_name: str, max_len: int
) -> list[tuple[str, bytes]]:
    """
    Build in-memory text files for domain lists.

    Filenames follow the pattern:
        <base_name>.txt
        <base_name>-2.txt
        <base_name>-3.txt  …

    Returns
    -------
    list of (filename, utf-8 bytes)
    """
    chunks = _split_chunks(items, max_len)
    result: list[tuple[str, bytes]] = []
    for i, chunk in enumerate(chunks):
        suffix = f"-{i + 1}" if i > 0 else ""
        filename = f"{base_name}{suffix}.txt"
        content = "\n".join(chunk) + "\n"
        result.append((filename, content.encode("utf-8")))

    logger.info(
        "make_domain_files: %d item(s) → %d file(s) (chunk size %d)",
        len(items), len(result), max_len,
    )
    return result


def make_ip_files(
    items: list[str], base_name: str, max_len: int
) -> list[tuple[str, bytes]]:
    """
    Build in-memory .bat files for IP route lists.

    Filenames follow the pattern:
        <base_name>.bat
        <base_name>-2.bat
        <base_name>-3.bat  …

    Returns
    -------
    list of (filename, utf-8 bytes)
    """
    chunks = _split_chunks(items, max_len)
    result: list[tuple[str, bytes]] = []
    for i, chunk in enumerate(chunks):
        suffix = f"-{i + 1}" if i > 0 else ""
        filename = f"{base_name}{suffix}.bat"
        content = "\n".join(chunk) + "\n"
        result.append((filename, content.encode("utf-8")))

    logger.info(
        "make_ip_files: %d item(s) → %d file(s) (chunk size %d)",
        len(items), len(result), max_len,
    )
    return result
