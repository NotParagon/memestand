#!/usr/bin/env python3
"""Allowlist for URLs that are written into href/src or into ranked data.

Allowed:
  - absolute https:// URLs (scheme is case-insensitive; the rest is kept as written)
  - site-relative paths that start with a single "/"
  - scheme-less relative paths (images/a.jpg, ../meme/x/, ./, #content)

Dropped (empty string, one warning each):
  javascript:, data:, vbscript:, http:, any other scheme, protocol-relative
  ("//..."), backslashes, and whitespace or control-character obfuscations
  such as "java\\tscript:" (browsers strip those before parsing the scheme).
"""
import sys
import unicodedata

_warned = set()


def reset_warnings():
    """Clear the once-per-URL warning set. Tests use this."""
    _warned.clear()


def _unsafe_char(ch):
    o = ord(ch)
    if o < 33 or o == 127:  # C0 controls, space, DEL
        return True
    cat = unicodedata.category(ch)
    return cat[0] in {"C", "Z"}  # controls, format, surrogates, any whitespace


def _warn(url, context):
    key = (url, context)
    if key in _warned:
        return
    _warned.add(key)
    shown = url if isinstance(url, str) else repr(url)
    shown = shown.encode("unicode_escape").decode("ascii")
    if len(shown) > 180:
        shown = shown[:180] + "..."
    where = f" ({context})" if context else ""
    print(f"  ! WARNING: dropped unsafe URL{where}: {shown}", file=sys.stderr)


def _has_scheme(url):
    """True when url begins with an RFC 3986 scheme, e.g. javascript: or http:.
    Scheme characters are ASCII only, so a non-ASCII letter cannot hide one."""
    if not url or not ("A" <= url[0] <= "Z" or "a" <= url[0] <= "z"):
        return False
    for ch in url:
        if ch == ":":
            return True
        if not (("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in "+-."):
            return False
    return False


def _https_has_host(url):
    rest = url[8:]  # after "https://" (any case; caller checks the prefix length)
    if not rest or rest[0] in "/\\#?":
        return False
    hostport = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = hostport.rsplit("@", 1)[-1]
    return bool(host) and host not in {".", ".."}


def safe_url(url, context=""):
    """Return url when it may be used as href/src. Otherwise "" and a warning.

    Empty and None are not warnings: a meme with no source simply has no link.
    A non-empty rejected value is logged once per (url, context) pair.
    """
    if url is None:
        return ""
    if not isinstance(url, str):
        _warn(str(url), context)
        return ""
    if url == "":
        return ""
    if any(_unsafe_char(ch) for ch in url) or "\\" in url:
        _warn(url, context)
        return ""
    if url.lower().startswith("https://"):
        if _https_has_host(url):
            return url
        _warn(url, context)
        return ""
    # "//cdn.example/a.js" is protocol-relative. "///x" and "/\\x" are too,
    # once a browser treats "\\" as "/".
    if url.startswith("//") or (url.startswith("/") and len(url) > 1 and url[1] in "/\\"):
        _warn(url, context)
        return ""
    if _has_scheme(url):
        _warn(url, context)
        return ""
    return url
