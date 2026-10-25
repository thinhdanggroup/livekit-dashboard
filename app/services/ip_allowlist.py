"""IP allowlist store for restricting dashboard access by source IP.

An empty stored list means "allow all" (the feature is off). A middleware
(added separately) calls is_allowed(ip) on every request and returns a
flat 403 when it is False -- so a bug here can lock an operator out of
their own dashboard with no recovery path short of editing the server's
filesystem directly.

To prevent that: save_allowlist() always ensures the requester's own IP
is present in the final list whenever that list is non-empty, whether or
not the operator typed it themselves. Submitting a blank/whitespace-only
value is treated as "turn the allowlist off" and always clears to the
empty (allow-all) list, regardless of requester_ip -- it must not be
reinterpreted as "allow only me".

Config is stored in a JSON file (path via IP_ALLOWLIST_FILE env var).
Schema: {"ips": ["1.2.3.4", ...]}
"""

import json
import logging
import os
import threading


logger = logging.getLogger(__name__)

_STORE_PATH = os.environ.get("IP_ALLOWLIST_FILE", "/tmp/ip_allowlist.json")
_LOCK = threading.Lock()


def _load() -> dict:
    """Load the raw store contents.

    Any failure to read or parse the store (missing file, a directory at
    the configured path, a permission error, invalid JSON, or
    non-UTF-8/undecodable bytes) must never propagate -- it is treated the
    same as "no store yet" so that a corrupt or misconfigured store fails
    open (allow-all) rather than locking every operator out.

    A missing file is the NORMAL state for a fresh/default install where
    nobody has configured an allowlist yet, and is_allowed() runs on every
    request -- so that case is handled silently (no log). Anything else
    (permission denied, a directory at the path, malformed JSON, non-UTF-8
    bytes, etc.) indicates a real, unexpected problem worth a warning.
    """
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("ip_allowlist store unreadable at %s (%s); treating as empty", _STORE_PATH, exc)
        return {}


def _save(cfg: dict) -> None:
    """Write the store atomically: write to a temp file in the same
    directory, then os.replace() it into place, so a concurrent reader
    never sees a partially-written file."""
    directory = os.path.dirname(_STORE_PATH) or "."
    tmp_path = os.path.join(directory, f".{os.path.basename(_STORE_PATH)}.tmp-{os.getpid()}-{threading.get_ident()}")
    with open(tmp_path, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp_path, _STORE_PATH)


def _parse_ips(raw: str) -> list[str]:
    """Split a comma-separated string into a deduped list of non-blank IPs."""
    seen: list[str] = []
    for part in raw.split(","):
        ip = part.strip()
        if ip and ip not in seen:
            seen.append(ip)
    return seen


def get_allowlist() -> list[str]:
    """Return the configured allowlist, or [] (allow-all) for any malformed store.

    Only a dict whose "ips" key is a list of strings is honored. Any other
    shape -- a bare list, a string, null, a list containing non-strings,
    etc. -- is treated as "no allowlist configured" rather than raising or
    being coerced into something that could accidentally deny everyone
    (e.g. list()-exploding a string into single-character "IPs").
    """
    cfg = _load()
    if not isinstance(cfg, dict):
        return []
    ips = cfg.get("ips", [])
    if not isinstance(ips, list) or not all(isinstance(ip, str) for ip in ips):
        return []
    return list(ips)


def save_allowlist(raw: str, requester_ip: str) -> list[str]:
    requester_ip = requester_ip.strip()

    if not raw.strip():
        ips: list[str] = []
    else:
        ips = _parse_ips(raw)
        if ips and requester_ip not in ips:
            ips.append(requester_ip)

    with _LOCK:
        cfg = _load()
        if not isinstance(cfg, dict):
            # Self-heal a malformed store (e.g. a bare `[]` file) instead of
            # crashing on cfg["ips"] = ... below; a save is an explicit admin
            # remediation action, so rewriting it to the expected shape is safe.
            cfg = {}
        cfg["ips"] = ips
        _save(cfg)
    return ips


def is_allowed(ip: str) -> bool:
    ips = get_allowlist()
    if not ips:
        return True
    return ip in ips
