"""Global search route."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from typing import Optional

from app.services.livekit import LiveKitClient, get_livekit_client
from app.services import search as search_service
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token


router = APIRouter()


@router.get("/search", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def search_view(
    request: Request,
    q: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Global cross-entity search."""
    query = (q or "").strip()
    results = await search_service.search_all(lk, query) if query else []

    counts: dict[str, int] = {"room": 0, "participant": 0, "egress": 0, "ingress": 0}
    for r in results:
        counts[r.kind] = counts.get(r.kind, 0) + 1

    return request.app.state.templates.TemplateResponse(
        request,
        "search/results.html.j2",
        {
            "request": request,
            "q": query,
            "results": results,
            "counts": counts,
            "total": len(results),
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
        },
    )
