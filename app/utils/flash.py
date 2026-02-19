"""Session-backed one-shot flash messages.

Usage
-----
Setting a flash (in a route before redirecting)::

    from app.utils.flash import flash
    flash(request, "Dispatch created.", "success")
    return RedirectResponse(...)

Reading the flash (in the route that renders the page after the redirect)::

    from app.utils.flash import get_flash
    msg, kind = get_flash(request)   # kind: "success" | "danger" | "warning" | "info"
"""

from typing import Optional, Tuple

from fastapi import Request

_SESSION_KEY = "_flash"


def flash(request: Request, message: str, kind: str = "info") -> None:
    """Store a flash message in the session (overwrites any previous one)."""
    request.session[_SESSION_KEY] = {"message": message, "kind": kind}


def get_flash(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """Pop and return (message, kind) from the session, or (None, None)."""
    data = request.session.pop(_SESSION_KEY, None)
    if data:
        return data["message"], data["kind"]
    return None, None
