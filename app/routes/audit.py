"""Audit log route — shows recent operator actions."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import audit_log
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/audit", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def audit_index(request: Request):
    entries = audit_log.list_entries(limit=200)
    return request.app.state.templates.TemplateResponse(
        request,
        "audit/index.html.j2",
        {
            "request": request,
            "entries": entries,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/audit/clear", dependencies=[Depends(requires_admin)])
async def clear_audit_log(request: Request, csrf_token: str = Form(...)):
    await verify_csrf_token(request)
    audit_log.clear()
    return RedirectResponse(url="/audit", status_code=303)
