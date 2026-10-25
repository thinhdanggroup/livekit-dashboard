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
import os


_STORE_PATH = os.environ.get("IP_ALLOWLIST_FILE", "/tmp/ip_allowlist.json")


def _load() -> dict:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(cfg: dict) -> None:
    with open(_STORE_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _parse_ips(raw: str) -> list[str]:
    """Split a comma-separated string into a deduped list of non-blank IPs."""
    seen: list[str] = []
    for part in raw.split(","):
        ip = part.strip()
        if ip and ip not in seen:
            seen.append(ip)
    return seen


def get_allowlist() -> list[str]:
    cfg = _load()
    return list(cfg.get("ips", []))


def save_allowlist(raw: str, requester_ip: str) -> list[str]:
    if not raw.strip():
        ips: list[str] = []
    else:
        ips = _parse_ips(raw)
        if ips and requester_ip not in ips:
            ips.append(requester_ip)

    cfg = _load()
    cfg["ips"] = ips
    _save(cfg)
    return ips


def is_allowed(ip: str) -> bool:
    ips = get_allowlist()
    if not ips:
        return True
    return ip in ips
