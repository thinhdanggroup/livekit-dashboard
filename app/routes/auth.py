"""Authentication routes"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    """Logout page (HTTP Basic Auth doesn't have server-side logout)"""
    return request.app.state.templates.TemplateResponse(
        "logout.html.j2",
        {
            "request": request,
        },
    )
