"""Alert rules management routes."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import alerts as alert_service
from app.services import notifications
from app.services.dashboard import gather_dashboard_stats
from app.services.livekit import LiveKitClient, get_livekit_client
from app.security.basic_auth import requires_admin, get_current_user
from app.security.csrf import get_csrf_token, verify_csrf_token


router = APIRouter()


@router.get("/alerts", response_class=HTMLResponse, dependencies=[Depends(requires_admin)])
async def list_alerts(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
    stats = await gather_dashboard_stats(lk)
    evaluated = alert_service.evaluate_all(stats)
    triggered = [rule for rule, is_triggered in evaluated if is_triggered]
    notifications.fire_webhook(triggered)

    notif_config = notifications.get_config()
    return request.app.state.templates.TemplateResponse(
        request,
        "alerts/index.html.j2",
        {
            "request": request,
            "evaluated": evaluated,
            "stats": stats,
            "metrics": alert_service.METRICS,
            "operators": alert_service.OPERATORS,
            "severities": alert_service.SEVERITIES,
            "notif_config": notif_config,
            "current_user": get_current_user(request),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/alerts", dependencies=[Depends(requires_admin)])
async def create_alert(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    metric: str = Form(...),
    operator: str = Form(...),
    threshold: float = Form(...),
    severity: str = Form("warning"),
):
    await verify_csrf_token(request)
    try:
        alert_service.create_rule(
            name=name,
            metric=metric,
            operator=operator,
            threshold=threshold,
            severity=severity,
        )
    except ValueError:
        pass
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/alerts/{rule_id}/delete", dependencies=[Depends(requires_admin)])
async def delete_alert(
    request: Request,
    rule_id: str,
    csrf_token: str = Form(...),
):
    await verify_csrf_token(request)
    alert_service.delete_rule(rule_id)
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/alerts/{rule_id}/toggle", dependencies=[Depends(requires_admin)])
async def toggle_alert(
    request: Request,
    rule_id: str,
    csrf_token: str = Form(...),
):
    await verify_csrf_token(request)
    alert_service.toggle_rule(rule_id)
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/alerts/notify/configure", dependencies=[Depends(requires_admin)])
async def configure_notifications(
    request: Request,
    csrf_token: str = Form(...),
    webhook_url: str = Form(""),
    cooldown_minutes: int = Form(10),
):
    await verify_csrf_token(request)
    notifications.save_config(webhook_url=webhook_url, cooldown_minutes=cooldown_minutes)
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/alerts/notify/send", dependencies=[Depends(requires_admin)])
async def send_notifications_now(
    request: Request,
    csrf_token: str = Form(...),
    lk: LiveKitClient = Depends(get_livekit_client),
):
    """Force-fire webhook for all currently-triggered rules, bypassing cooldown."""
    await verify_csrf_token(request)
    stats = await gather_dashboard_stats(lk)
    evaluated = alert_service.evaluate_all(stats)
    triggered = [rule for rule, is_triggered in evaluated if is_triggered]
    notifications.fire_webhook(triggered, force=True)
    return RedirectResponse(url="/alerts", status_code=303)
