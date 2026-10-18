"""Restricted browser-lane arguments; prohibit chrome/file/data/javascript URLs."""
import re
from urllib.parse import urlsplit

_ALLOWED_SCHEMES=frozenset(("https","http"))
_TARGET=re.compile(r"^[A-Fa-f0-9]{8,64}$")


def normalize_url(url):
    if type(url) is not str or not 1<=len(url)<=2048 or any(ord(c)<32 for c in url):
        raise ValueError("invalid browser URL")
    url=url.strip()
    parts=urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise ValueError("only HTTP(S) navigation is allowed")
    if parts.username or parts.password:
        raise ValueError("embedded URL credentials are disallowed")
    return url


def validate_selector(value):
    if type(value) is not str or not 1<=len(value)<=1000 or value!=value.strip():
        raise ValueError("invalid CSS selector")
    if any(ord(c)<32 for c in value):
        raise ValueError("invalid CSS selector")
    return value


def validate_value(value):
    if type(value) is not str or len(value)>10000 or any(c=="\x00" for c in value):
        raise ValueError("invalid form value")
    return value


def validate_target_id(value):
    if type(value) is not str or not _TARGET.fullmatch(value):
        raise ValueError("invalid CDP target id")
    return value
