"""Analytics routes — latency percentile dashboard."""

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.security.basic_auth import requires_admin, get_current_user
from app.services import latency_samples


router = APIRouter()


def _format_coverage(coverage_seconds: float) -> str:
    """Render a seconds duration as a short "Xh Ym" (or "Ym") label."""
    total_minutes = max(0, int(coverage_seconds // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


@router.get("/analytics/latency", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def latency_page(request: Request, window: str = "1h"):
    window_seconds = 3600 if window == "1h" else 86400

    op_stats = []
    for op_type in latency_samples.list_op_types():
        oldest_ts = latency_samples.oldest_sample_ts(op_type, window_seconds)
        coverage_label = None
        if oldest_ts is not None:
            coverage_label = _format_coverage(time.time() - oldest_ts)

        op_stats.append({
            "op_type": op_type,
            "stats": latency_samples.percentiles(op_type, window_seconds),
            "slowest": sorted(
                latency_samples.recent_samples(op_type, window_seconds, limit=50),
                key=lambda s: s[1],
                reverse=True,
            )[:10],
            "coverage_label": coverage_label,
        })

    return request.app.state.templates.TemplateResponse(
        request,
        "analytics/latency.html.j2",
        {
            "request": request,
            "current_user": get_current_user(request),
            "op_stats": op_stats,
            "window": window,
        },
    )
