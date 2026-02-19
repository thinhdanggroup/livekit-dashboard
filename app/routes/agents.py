"""Agent dispatch management routes"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security.basic_auth import get_current_user, requires_admin
from app.security.csrf import get_csrf_token, verify_csrf_token
from app.services.livekit import LiveKitClient, get_livekit_client
from app.utils.flash import flash, get_flash

router = APIRouter()

# Job status codes from livekit_agent.proto
_JOB_STATUS = {0: "pending", 1: "running", 2: "success", 3: "failed"}


def _ns_to_dt(ns: int) -> Optional[str]:
    """Convert nanosecond timestamp to human-readable UTC string."""
    if not ns:
        return None
    try:
        dt = datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)
        return dt.strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return None


def _dispatch_summary(dispatch) -> dict:
    """Build a serialisable dict from an AgentDispatch proto object."""
    state = dispatch.state
    jobs = list(state.jobs) if state else []
    running = sum(1 for j in jobs if j.state and j.state.status == 1)
    overall_status = "running" if running > 0 else "pending"

    job_list = []
    for j in jobs:
        js = j.state
        job_list.append(
            {
                "id": j.id,
                "status": _JOB_STATUS.get(js.status if js else 0, "pending"),
                "started_at": _ns_to_dt(js.started_at if js else 0),
                "ended_at": _ns_to_dt(js.ended_at if js else 0),
                "worker_id": js.worker_id if js else "",
                "error": js.error if js else "",
            }
        )

    return {
        "id": dispatch.id,
        "agent_name": dispatch.agent_name or "(unnamed)",
        "agent_name_raw": dispatch.agent_name,
        "room": dispatch.room,
        "metadata": dispatch.metadata,
        "status": overall_status,
        "running_jobs": running,
        "total_jobs": len(jobs),
        "jobs": job_list,
        "created_at": _ns_to_dt(state.created_at if state else 0),
        "deleted_at": _ns_to_dt(state.deleted_at if state else 0),
    }


@router.get("/agents", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def agents_index(
    request: Request,
    force: Optional[str] = None,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Fleet overview — all dispatches grouped by agent_name.

    Pass ?force=1 to bypass the TTL cache and fetch live data immediately.
    """
    if force:
        from app.services import cache as dispatch_cache
        dispatch_cache.invalidate(lk.url)

    try:
        all_dispatches, latency = await lk.list_all_dispatches()
    except Exception as e:
        print(f"DEBUG: Error fetching dispatches: {e}")
        all_dispatches, latency = [], 0.0

    summaries = [_dispatch_summary(d) for d in all_dispatches]

    # Group by agent_name (raw value, so empty strings cluster together)
    agent_groups: dict = {}
    for s in summaries:
        key = s["agent_name"]
        agent_groups.setdefault(key, []).append(s)

    total_sessions = sum(s["running_jobs"] for s in summaries)

    flash_message, flash_type = get_flash(request)
    return request.app.state.templates.TemplateResponse(
        "agents/index.html.j2",
        {
            "request": request,
            "current_user": get_current_user(request),
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "agent_groups": agent_groups,
            "total_agents": len(agent_groups),
            "total_sessions": total_sessions,
            "total_dispatches": len(summaries),
            "latency_ms": round(latency * 1000, 2),
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


@router.get(
    "/agents/{agent_name:path}",
    response_class=HTMLResponse,
    dependencies=[Depends(requires_admin)],
)
async def agent_detail(
    request: Request,
    agent_name: str,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Per-agent detail — all dispatches where dispatch.agent_name matches."""
    try:
        all_dispatches, latency = await lk.list_all_dispatches()
    except Exception as e:
        print(f"DEBUG: Error fetching dispatches: {e}")
        all_dispatches, latency = [], 0.0

    # agent_name in URL is the display name; match against raw agent_name field
    # "(unnamed)" in URL maps to empty string in proto
    raw_name = "" if agent_name == "(unnamed)" else agent_name
    dispatches = [
        _dispatch_summary(d) for d in all_dispatches if d.agent_name == raw_name
    ]

    rooms = sorted({d["room"] for d in dispatches})
    total_sessions = sum(d["running_jobs"] for d in dispatches)

    # Aggregate job-level metrics across all dispatches
    all_jobs = [j for d in dispatches for j in d["jobs"]]
    total_jobs = len(all_jobs)
    running_jobs_count = sum(1 for j in all_jobs if j["status"] == "running")
    success_jobs_count = sum(1 for j in all_jobs if j["status"] == "success")
    failed_jobs_count = sum(1 for j in all_jobs if j["status"] == "failed")
    pending_jobs_count = sum(1 for j in all_jobs if j["status"] == "pending")
    success_rate = round(success_jobs_count / total_jobs * 100, 1) if total_jobs > 0 else 0.0

    agent_id = dispatches[0]["id"] if dispatches else None

    return request.app.state.templates.TemplateResponse(
        "agents/detail.html.j2",
        {
            "request": request,
            "current_user": get_current_user(request),
            "sip_enabled": lk.sip_enabled,
            "csrf_token": get_csrf_token(request),
            "agent_name": agent_name,
            "agent_id": agent_id,
            "dispatches": dispatches,
            "rooms": rooms,
            "total_sessions": total_sessions,
            "latency_ms": round(latency * 1000, 2),
            "total_jobs": total_jobs,
            "running_jobs_count": running_jobs_count,
            "success_jobs_count": success_jobs_count,
            "failed_jobs_count": failed_jobs_count,
            "pending_jobs_count": pending_jobs_count,
            "success_rate": success_rate,
        },
    )


@router.post("/agents/dispatch", dependencies=[Depends(requires_admin)])
async def create_dispatch(
    request: Request,
    csrf_token: str = Form(...),
    agent_name: str = Form(...),
    room: str = Form(...),
    metadata: str = Form(""),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Create an agent dispatch."""
    await verify_csrf_token(request)
    name = agent_name.strip()
    rm = room.strip()
    try:
        await lk.create_dispatch(agent_name=name, room=rm, metadata=metadata)
        flash(request, f"Agent '{name}' dispatched to room '{rm}'.", "success")
    except Exception as e:
        print(f"Error creating dispatch: {e}")
        flash(request, f"Failed to dispatch agent: {e}", "danger")
    return RedirectResponse(url="/agents", status_code=303)


@router.post(
    "/agents/{dispatch_id}/delete",
    dependencies=[Depends(requires_admin)],
)
async def delete_dispatch(
    request: Request,
    dispatch_id: str,
    csrf_token: str = Form(...),
    room: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Delete an agent dispatch."""
    await verify_csrf_token(request)
    try:
        await lk.delete_dispatch(dispatch_id=dispatch_id, room=room)
        flash(request, f"Dispatch '{dispatch_id}' deleted.", "success")
    except Exception as e:
        print(f"Error deleting dispatch {dispatch_id}: {e}")
        flash(request, f"Failed to delete dispatch: {e}", "danger")
    return RedirectResponse(url="/agents", status_code=303)
