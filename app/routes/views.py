"""Saved dashboard views routes."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import saved_views
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/views", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def list_views(request: Request):
    views = saved_views.list_views()
    return request.app.state.templates.TemplateResponse(
        request,
        "views/index.html.j2",
        {
            "request": request,
            "views": views,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/views", dependencies=[Depends(requires_admin)])
async def create_view(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    time_range: str = Form(""),
    q: str = Form(""),
    sort: str = Form("desc"),
    sort_by: str = Form("created_at"),
):
    await verify_csrf_token(request)
    if name.strip():
        saved_views.create_view(
            name=name,
            time_range=time_range,
            q=q,
            sort=sort,
            sort_by=sort_by,
        )
    return RedirectResponse(url="/views", status_code=303)


@router.post("/views/{view_id}/delete", dependencies=[Depends(requires_admin)])
async def delete_view(
    request: Request,
    view_id: str,
    csrf_token: str = Form(...),
):
    await verify_csrf_token(request)
    saved_views.delete_view(view_id)
    return RedirectResponse(url="/views", status_code=303)
