# LiveKit Dashboard - AI Coding Agent Instructions

## Project Overview

This is a **stateless, server-side rendered (SSR) FastAPI dashboard** for managing private LiveKit servers. The architecture prioritizes simplicity, security, and direct LiveKit SDK integration without external dependencies.

### Core Architecture Principles

- **Stateless Design**: No database, Redis, or persistent storage - all data fetched directly from LiveKit APIs
- **SSR with Progressive Enhancement**: Jinja2 templates + HTMX for dynamic updates
- **Security-First**: HTTP Basic Auth, CSRF protection, comprehensive security headers
- **Minimal Dependencies**: Only FastAPI, LiveKit SDK, and essential libraries

## Key Patterns & Conventions

### Route Structure (`app/routes/`)

Routes follow a consistent dependency injection pattern:
```python
@router.get("/endpoint", dependencies=[Depends(requires_admin)])
async def handler(
    request: Request,
    lk: LiveKitClient = Depends(get_livekit_client),
):
```

- **Authentication**: Use `Depends(requires_admin)` for protected routes
- **LiveKit Client**: Inject via `Depends(get_livekit_client)`
- **CSRF**: Use `verify_csrf_token(request)` for POST endpoints
- **Templates**: Access via `request.app.state.templates`

### LiveKit Service Layer (`app/services/livekit.py`)

The `LiveKitClient` wrapper provides:
- **Async-first design**: All methods return `Tuple[data, latency_ms]`
- **Built-in latency tracking**: Every API call measures response time
- **Error handling**: Graceful failures with meaningful error messages
- **Lazy initialization**: API instances created in async context

### Security Implementation

Located in `app/security/`:
- **`basic_auth.py`**: HTTP Basic Auth with constant-time comparison
- **`csrf.py`**: CSRF tokens using `itsdangerous` 
- **Security headers**: Set in `main.py` middleware (CSP, HSTS, etc.)

### Template Patterns (`app/templates/`)

- **Base template**: `base.html.j2` with blocks for content, scripts, styles
- **HTMX integration**: Use `hx-get`, `hx-post` for dynamic updates
- **CSRF tokens**: Available via `csrf_token(request)` global function
- **Responsive design**: Bootstrap-based with custom CSS

## Development Workflow

### Environment Setup
```bash
make install    # Install dependencies via Poetry
make env-example # Copy .env.example to .env
```

### Required Environment Variables
```bash
LIVEKIT_URL=https://your-livekit-server.com
LIVEKIT_API_KEY=your-api-key  
LIVEKIT_API_SECRET=your-api-secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure-password
APP_SECRET_KEY=$(openssl rand -hex 32)
```

### Development Commands
```bash
make dev        # Run with auto-reload
make test       # Run pytest suite
make test-cov   # Run with coverage report
make fmt        # Format with Black
make lint       # Lint with Ruff + mypy
```

### Docker Deployment
```bash
make docker-build && make docker-run
```

## LiveKit Integration Patterns

### API Response Handling
All LiveKit operations return `(data, latency)` tuples:
```python
rooms, latency = await lk.list_rooms()
participants, latency = await lk.list_participants(room_name)
```

### Error Handling
LiveKit errors are caught and converted to user-friendly messages in templates.

### Feature Flags
- **SIP Features**: Controlled by `ENABLE_SIP` environment variable
- **Debug Mode**: `DEBUG=true` enables additional logging and error details

## Code Style & Quality

- **Formatting**: Black with 100-character line length
- **Linting**: Ruff for fast Python linting
- **Type Checking**: mypy (gradual typing, not strict)
- **Testing**: pytest with async support

## Adding New Features

1. **Routes**: Create in `app/routes/` following existing patterns
2. **Templates**: Add to `app/templates/` with appropriate base inheritance  
3. **Services**: Extend `LiveKitClient` for new LiveKit functionality
4. **Static Assets**: Place in `app/static/` (CSS, JS, images)

## Important Files

- `app/main.py`: FastAPI app setup, middleware, security headers
- `app/services/livekit.py`: Core LiveKit SDK wrapper (994 lines)
- `app/security/`: Authentication and CSRF protection
- `Makefile`: Development workflow commands
- `pyproject.toml`: Poetry dependencies and tool configuration

## Testing Approach

- **Unit Tests**: Focus on LiveKit client and security functions
- **Integration Tests**: Test route handlers with mocked LiveKit responses
- **No UI Tests**: SSR approach minimizes JavaScript testing needs
