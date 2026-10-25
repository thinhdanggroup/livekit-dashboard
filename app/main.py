"""
LiveKit Dashboard - Main Application
Stateless SSR dashboard for LiveKit server management
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.routes import overview, rooms, egress, ingress, sip, settings, sandbox, auth, agents, homer, search, views, alerts, audit, diagnostics, events, analytics, report_rules
from app.security.csrf import get_csrf_token
from app.services import ip_allowlist
from app.services import report_rules as report_rules_service
from app.services import room_poller
from app.utils.formatters import format_duration, format_pct, status_color, format_number

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    # Startup
    print("🚀 LiveKit Dashboard starting up...")
    print(f"   LiveKit URL: {os.environ.get('LIVEKIT_URL', 'Not set')}")
    print(f"   SIP Enabled: {os.environ.get('ENABLE_SIP', 'false')}")
    print(f"   Homer Enabled: {os.environ.get('ENABLE_HOMER', 'false')}")

    # Verify required environment variables
    required_vars = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print(f"⚠️  WARNING: Missing required environment variables: {', '.join(missing_vars)}")
    else:
        print("✅ All required environment variables are set")

    background_tasks = [
        asyncio.create_task(report_rules_service.run_scheduler_loop()),
        asyncio.create_task(room_poller.run_poller_loop()),
    ]

    yield

    # Shutdown
    for task in background_tasks:
        task.cancel()
    # return_exceptions=True so one task's CancelledError doesn't prevent the
    # other background task from being awaited/cleaned up.
    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("👋 LiveKit Dashboard shutting down...")


# Create FastAPI app
app = FastAPI(
    title="LiveKit Dashboard",
    description="Self-hosted SSR dashboard for LiveKit server management",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,  # Disable Swagger UI in production
    redoc_url=None,  # Disable ReDoc in production
)

# Add security middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SECRET_KEY", "dev-secret-key-change-in-production"),
)


@app.middleware("http")
async def ensure_csrf_token(request: Request, call_next):
    """Ensure every request has a CSRF token available for templates."""
    get_csrf_token(request)
    return await call_next(request)


@app.middleware("http")
async def enforce_readonly_mode(request: Request, call_next):
    """Block mutating requests when DASHBOARD_ROLE=readonly."""
    if os.environ.get("DASHBOARD_ROLE", "admin").lower() == "readonly":
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not request.url.path.startswith("/auth"):
                from fastapi.responses import Response as _Resp
                return _Resp("Read-only mode — mutations are disabled.", status_code=403)
    return await call_next(request)


# Add CORS middleware (restrictive by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],  # No CORS by default for security
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# IMPORTANT: Starlette builds the middleware stack with the LAST-registered
# `@app.middleware("http")`/`add_middleware()` call as the OUTERMOST layer
# (it runs first, before anything registered earlier). This middleware is
# therefore registered after CORSMiddleware and enforce_readonly_mode above
# so that it executes BEFORE both of them -- a blocked IP must get a flat,
# generic "Access denied." 403 and never reach CORS or readonly-mode logic,
# which would otherwise leak information about the app's state to a caller
# that shouldn't get any response at all. (add_security_headers, registered
# further below after the routers, ends up outermost of all -- that's fine,
# it only decorates whatever response comes back, it never rejects one.)
@app.middleware("http")
async def enforce_ip_allowlist(request: Request, call_next):
    """Block requests from IPs not present on a configured allowlist.

    An empty/unconfigured allowlist means "allow all" (see
    app.services.ip_allowlist), so this is a no-op until an operator
    explicitly configures one via Settings. If the allowlist check itself
    raises for any reason (e.g. an unforeseen bug in the store), we fail
    OPEN -- allow the request through -- rather than locking every
    operator out of the dashboard because of a corrupted config file.
    """
    if request.url.path == "/health":
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    try:
        allowed = ip_allowlist.is_allowed(client_ip)
    except Exception:
        logger.exception("enforce_ip_allowlist: is_allowed() raised; failing open (allowing request)")
        allowed = True
    if not allowed:
        from fastapi.responses import Response as _Resp
        return _Resp("Access denied.", status_code=403)
    return await call_next(request)


# Setup Jinja2 templates
templates = Jinja2Templates(directory="app/templates")


# Add custom template globals
CSS_VERSION = "0.1.0"

templates.env.globals["css_version"] = CSS_VERSION
templates.env.globals["homer_enabled"] = lambda: os.environ.get("ENABLE_HOMER", "false").lower() == "true"
templates.env.globals["sip_enabled"] = lambda: os.environ.get("ENABLE_SIP", "false").lower() == "true"
templates.env.globals["is_readonly"] = lambda: os.environ.get("DASHBOARD_ROLE", "admin").lower() == "readonly"


def _datetimeformat(value: int) -> str:
    """Format a Unix timestamp (seconds) as a human-readable string."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


templates.env.filters["datetimeformat"] = _datetimeformat


def _proto_map_tojson(value) -> str:
    """Convert a protobuf ScalarMapContainer (or any dict-like) to a JSON string."""
    import json
    try:
        return json.dumps(dict(value))
    except Exception:
        return "{}"


templates.env.filters["proto_map_tojson"] = _proto_map_tojson

# Formatting helpers (from app.utils.formatters)
templates.env.filters["duration"] = format_duration
templates.env.filters["pct"] = format_pct
templates.env.filters["status_color"] = status_color
templates.env.filters["numformat"] = format_number

# Store templates in app state for route access
app.state.templates = templates

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(overview.router, tags=["Overview"])
app.include_router(agents.router, tags=["Agents"])
app.include_router(rooms.router, tags=["Rooms"])
app.include_router(egress.router, tags=["Egress"])
app.include_router(ingress.router, tags=["Ingress"])
app.include_router(sip.router, tags=["SIP"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(sandbox.router, tags=["Sandbox"])
app.include_router(auth.router, tags=["Auth"])
app.include_router(homer.router, tags=["Homer"])
app.include_router(search.router, tags=["Search"])
app.include_router(views.router, tags=["Views"])
app.include_router(alerts.router, tags=["Alerts"])
app.include_router(audit.router, tags=["Audit"])
app.include_router(diagnostics.router, tags=["Diagnostics"])
app.include_router(events.router, tags=["Events"])
app.include_router(analytics.router, tags=["Analytics"])
app.include_router(report_rules.router, tags=["Reports"])


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Only add HSTS in production with HTTPS
    if os.environ.get("DEBUG", "false").lower() != "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy (adjust as needed)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self';"
    )
    response.headers["Content-Security-Policy"] = csp

    # Disable caching for HTML pages
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 page"""
    return templates.TemplateResponse(request, 
        "base.html.j2",
        {
            "request": request,
            "error": "Page not found",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Custom 500 page"""
    return templates.TemplateResponse(request, 
        "base.html.j2",
        {
            "request": request,
            "error": "Internal server error",
        },
        status_code=500,
    )


# Health check endpoint (no auth required)
@app.get("/health", response_class=HTMLResponse)
async def health_check():
    """Health check endpoint"""
    return HTMLResponse(content="OK", status_code=200)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if debug else "warning",
    )
