"""Minimal outbound HTTP POST helper built on urllib.

Usage
-----
Callers import the module so tests can patch ``post_json`` directly::

    import app.utils.http as http_util
    result = http_util.post_json(url, payload_json)
    # result: {"status": int | None, "body": str, "error": str | None}
"""

import urllib.error
import urllib.request


def post_json(url: str, payload: str, timeout: float = 5.0) -> dict:
    """POST a JSON string to ``url`` and return a normalized result dict.

    An HTTP error response still counts as a completed delivery, so its
    status code is returned with ``error`` set to None. Transport failures
    (timeout, DNS, connection refused) yield ``status`` None and ``error``
    set to the exception message.
    """
    result: dict = {"status": None, "body": "", "error": None}
    try:
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={"Content-Type": "application/json", "User-Agent": "livekit-dashboard/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = {
                "status": resp.status,
                "body": resp.read(512).decode(errors="replace"),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        result = {"status": e.code, "body": e.read(256).decode(errors="replace"), "error": None}
    except Exception as exc:
        result = {"status": None, "body": "", "error": str(exc)}
    return result
