"""Indicators of compromise, read deterministically - defanged forms included (Phase 52).

Analysts write indicators so they cannot be clicked: `hxxp://evil[.]example`, `10.0.0[.]5`,
`user[@]corp.example`. Each is refanged before matching, and reported in its usable form with the
line it came from. No model is involved: an indicator is a pattern, and a pattern either matches or
it does not.

Kinds: IPv4, domain, URL, e-mail, MD5 / SHA-1 / SHA-256, CVE, Windows file path, registry key.
A domain must end in a letters-only label of two or more characters and not be a file name the line
also names as a path (`powershell.exe` is a process, not a host).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from enum import StrEnum

from app.schemas.common import JarvisModel


class IocKind(StrEnum):
    IPV4 = "ipv4"
    DOMAIN = "domain"
    URL = "url"
    EMAIL = "email"
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    CVE = "cve"
    FILE_PATH = "file_path"
    REGISTRY_KEY = "registry_key"


class Ioc(JarvisModel):
    kind: IocKind
    value: str
    # As written, when it was defanged.
    written: str = ""
    source: str = ""


def _scheme(match: re.Match[str]) -> str:
    return match.group(0).lower().replace("xx", "tt")


def _unbracket(match: re.Match[str]) -> str:
    return match.group(0)[1:-1]


_REFANG: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (re.compile(r"hxxps?", re.IGNORECASE), _scheme),
    (re.compile(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]|\(dot\)", re.IGNORECASE), "."),
    (re.compile(r"\[:\]|\[://\]", re.IGNORECASE), _unbracket),
    (re.compile(r"\[@\]|\[at\]|\(at\)", re.IGNORECASE), "@"),
]


def refang(text: str) -> str:
    for pattern, replace in _REFANG:
        text = pattern.sub(replace, text)
    return text


_URL = re.compile(r"\b(?:https?|ftp)://[^\s\"'<>()\[\]]+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_DOMAIN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE)
_HASHES = [
    (IocKind.SHA256, re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE)),
    (IocKind.SHA1, re.compile(r"\b[a-f0-9]{40}\b", re.IGNORECASE)),
    (IocKind.MD5, re.compile(r"\b[a-f0-9]{32}\b", re.IGNORECASE)),
]
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
# Directory names may hold spaces ("Program Files"); the last segment may not, nor a comma (the
# rundll32 "x.dll,Start" entry point is not part of the file).
_PATH = re.compile(r"\b[a-z]:\\(?:[^\\\n\"'<>|:*?]+\\)*[^\\\s\"'<>|:*?,]+", re.IGNORECASE)
_REGISTRY = re.compile(
    r"\b(?:HKLM|HKCU|HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|HKU|HKCR)\\[^\s\"']+", re.IGNORECASE
)
# A host name ends in a top-level domain: a common one, or any two-letter country code. Without
# this, a .NET type in a decoded script ("Net.WebClient") reads as a domain.
_TLDS = frozenset(
    "com net org edu gov mil int info biz io co ai app dev cloud online site xyz top tech store "
    "example test invalid local localhost internal corp lan home onion".split()
)
# File extensions that make a dotted name a file, not a host.
_FILE_SUFFIX = re.compile(
    r"\.(exe|dll|sys|bat|cmd|ps1|psm1|vbs|js|jar|zip|rar|7z|txt|log|json|xml|csv|docx?|xlsx?|pdf|"
    r"png|jpe?g|lnk|tmp|dat|bin|msi|scr|hta|py|sh|evtx|ini|cfg)$",
    re.IGNORECASE,
)


def extract(text: str, source: str = "") -> list[Ioc]:
    """Every indicator in one line, refanged, each once."""
    clean = refang(text)
    defanged = clean != text
    found: dict[tuple[IocKind, str], Ioc] = {}

    def add(kind: IocKind, value: str) -> None:
        key = (kind, value.lower() if kind is not IocKind.FILE_PATH else value)
        if key not in found:
            found[key] = Ioc(
                kind=kind, value=value, written=text.strip() if defanged else "", source=source
            )

    urls = [m.group(0).rstrip(".,;") for m in _URL.finditer(clean)]
    for url in urls:
        add(IocKind.URL, url)
    for match in _EMAIL.finditer(clean):
        add(IocKind.EMAIL, match.group(0))
    for match in _IPV4.finditer(clean):
        try:
            ipaddress.IPv4Address(match.group(0))
        except ValueError:
            continue
        add(IocKind.IPV4, match.group(0))
    # Word boundaries keep a SHA-1 from matching inside a SHA-256, and an MD5 inside either.
    for kind, pattern in _HASHES:
        for match in pattern.finditer(clean):
            add(kind, match.group(0).lower())
    for match in _CVE.finditer(clean):
        add(IocKind.CVE, match.group(0).upper())
    paths = [m.group(0) for m in _PATH.finditer(clean)]
    for path in paths:
        add(IocKind.FILE_PATH, path)
    for match in _REGISTRY.finditer(clean):
        add(IocKind.REGISTRY_KEY, match.group(0))
    emails = {i.value.lower() for i in found.values() if i.kind is IocKind.EMAIL}
    for match in _DOMAIN.finditer(clean):
        domain = match.group(0)
        tld = domain.rsplit(".", 1)[-1].lower()
        if len(tld) != 2 and tld not in _TLDS:
            continue
        if _FILE_SUFFIX.search(domain) or any(domain.lower() in e for e in emails):
            continue
        if _IPV4.fullmatch(domain):
            continue
        add(IocKind.DOMAIN, domain.lower())
    return list(found.values())
