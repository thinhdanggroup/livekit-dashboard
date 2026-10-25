"""Scheduled report rules management routes."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import report_rules as report_rule_service
from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/reports", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def list_report_rules(request: Request):
    rules = report_rule_service.list_rules()
    return request.app.state.templates.TemplateResponse(
        request,
        "reports/index.html.j2",
        {
            "request": request,
            "rules": rules,
            "schedule_types": report_rule_service.SCHEDULE_TYPES,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/reports", dependencies=[Depends(requires_admin)])
async def create_report_rule(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    schedule_type: str = Form(...),
    interval_minutes: str = Form(""),
    daily_time: str = Form(""),
):
    await verify_csrf_token(request)
    try:
        report_rule_service.create_rule(
            name=name,
            schedule_type=schedule_type,
            interval_minutes=int(interval_minutes) if interval_minutes else None,
            daily_time=daily_time or None,
        )
    except ValueError:
        pass
    return RedirectResponse(url="/reports", status_code=303)


@router.post("/reports/{rule_id}/delete", dependencies=[Depends(requires_admin)])
async def delete_report_rule(
    request: Request,
    rule_id: str,
    csrf_token: str = Form(...),
):
    await verify_csrf_token(request)
    report_rule_service.delete_rule(rule_id)
    return RedirectResponse(url="/reports", status_code=303)


@router.post("/reports/{rule_id}/toggle", dependencies=[Depends(requires_admin)])
async def toggle_report_rule(
    request: Request,
    rule_id: str,
    csrf_token: str = Form(...),
):
    await verify_csrf_token(request)
    report_rule_service.toggle_rule(rule_id)
    return RedirectResponse(url="/reports", status_code=303)


@router.post("/reports/{rule_id}/run-now", dependencies=[Depends(requires_admin)])
async def run_report_rule_now(
    request: Request,
    rule_id: str,
    csrf_token: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Run a single report rule immediately, bypassing the due-check."""
    await verify_csrf_token(request)
    rule = report_rule_service.get_rule(rule_id)
    if rule is not None:
        await report_rule_service.run_rule_now(rule, lk)
    return RedirectResponse(url="/reports", status_code=303)
