"""
LiveKit Dashboard - Main Application
Stateless SSR dashboard for LiveKit server management
"""

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.routes import overview, rooms, egress, sip, settings, sandbox, auth
from app.security.csrf import get_csrf_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    # Startup
    print("🚀 LiveKit Dashboard starting up...")
    print(f"   LiveKit URL: {os.environ.get('LIVEKIT_URL', 'Not set')}")
    print(f"   SIP Enabled: {os.environ.get('ENABLE_SIP', 'false')}")

    # Verify required environment variables
    required_vars = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print(f"⚠️  WARNING: Missing required environment variables: {', '.join(missing_vars)}")
    else:
        print("✅ All required environment variables are set")

    yield

    # Shutdown
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

# Add CORS middleware (restrictive by default)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],  # No CORS by default for security
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Setup Jinja2 templates
templates = Jinja2Templates(directory="app/templates")


# Add custom template functions
def csrf_token_function(request: Request) -> str:
    """Template function to get CSRF token"""
    return get_csrf_token(request)


templates.env.globals["csrf_token"] = csrf_token_function

# Store templates in app state for route access
app.state.templates = templates

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(overview.router, tags=["Overview"])
app.include_router(rooms.router, tags=["Rooms"])
app.include_router(egress.router, tags=["Egress"])
app.include_router(sip.router, tags=["SIP"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(sandbox.router, tags=["Sandbox"])
app.include_router(auth.router, tags=["Auth"])


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
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
