# LiveKit Dashboard Architecture

## Overview

LiveKit Dashboard is a **stateless**, server-side rendered (SSR) web application built with FastAPI and Jinja2 templates. It provides a management interface for LiveKit servers using only the LiveKit Python SDK.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
│                    (HTTP Basic Auth)                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS (Production)
                            │ HTTP (Development)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Reverse Proxy (Optional)                     │
│              nginx / Caddy / Traefik with TLS                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Application (SSR)                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │               Middleware Stack                            │ │
│  │  • SessionMiddleware (CSRF token storage)                 │ │
│  │  • CORSMiddleware (restrictive by default)                │ │
│  │  • Security Headers (HSTS, CSP, X-Frame-Options)          │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                  Route Handlers                           │ │
│  │  • overview.py    - Dashboard/health                      │ │
│  │  • rooms.py       - Room management                       │ │
│  │  • egress.py      - Recording management                  │ │
│  │  • sip.py         - SIP telephony (optional)              │ │
│  │  • settings.py    - Configuration view                    │ │
│  │  • sandbox.py     - Token generator                       │ │
│  │  • auth.py        - Authentication                        │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Security Layer                               │ │
│  │  • basic_auth.py  - HTTP Basic Auth                       │ │
│  │  • csrf.py        - CSRF token generation/validation      │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │           Services / Business Logic                       │ │
│  │  • livekit.py     - LiveKit SDK wrapper                   │ │
│  │    - RoomServiceClient                                    │ │
│  │    - EgressServiceClient                                  │ │
│  │    - SIPServiceClient (optional)                          │ │
│  │    - Token generation                                     │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │            Template Rendering (Jinja2)                    │ │
│  │  • base.html.j2       - Base layout                       │ │
│  │  • index.html.j2      - Overview                          │ │
│  │  • rooms/*.html.j2    - Room pages                        │ │
│  │  • egress/*.html.j2   - Egress pages                      │ │
│  │  • sip/*.html.j2      - SIP pages                         │ │
│  │  • settings.html.j2   - Settings                          │ │
│  │  • sandbox.html.j2    - Token generator                   │ │
│  └───────────────────────┬───────────────────────────────────┘ │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Static Assets                                │ │
│  │  • CSS (Bootstrap + custom)                               │ │
│  │  • JavaScript (HTMX + utilities)                          │ │
│  └───────────────────────────────────────────────────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │ LiveKit SDK API Calls
                            │ (WebSocket & HTTP)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LiveKit Server                               │
│  • Room Management                                              │
│  • Participant Management                                       │
│  • Egress (Recording)                                           │
│  • SIP (Telephony)                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Request Flow

### Typical Request Flow

1. **User Request**
   - User accesses a page (e.g., `/rooms`)
   - Browser sends HTTP request with Basic Auth header

2. **Authentication**
   - Request reaches FastAPI middleware
   - `requires_admin` dependency verifies credentials
   - If invalid, returns 401 Unauthorized
   - If valid, proceeds to route handler

3. **CSRF Protection (POST requests)**
   - For POST/PUT/DELETE requests
   - Validates CSRF token from form data
   - If invalid, returns 403 Forbidden
   - If valid, proceeds

4. **Route Handler**
   - Extracts route parameters and query strings
   - Calls LiveKitClient service methods
   - Fetches data directly from LiveKit server

5. **LiveKit SDK Call**
   - LiveKitClient makes API call to LiveKit server
   - Returns data (rooms, participants, etc.)
   - No caching or persistence

6. **Template Rendering**
   - Route handler passes data to Jinja2 template
   - Template renders HTML with data
   - CSRF token generated and embedded

7. **Response**
   - HTML response sent to browser
   - Security headers added by middleware
   - Browser displays page

### HTMX Auto-Refresh Flow

For pages with auto-refresh (using HTMX):

1. **Initial Page Load**
   - Full HTML page rendered and sent

2. **HTMX Polling**
   - Every N seconds, HTMX sends GET request with `?partial=1`
   - Request includes `hx-trigger="every 5s"`

3. **Partial Update**
   - Route handler detects `partial=1` parameter
   - Returns only the updated section HTML
   - HTMX swaps the content in place

4. **Benefits**
   - Real-time updates without WebSockets
   - Reduced bandwidth (only partial HTML)
   - Progressive enhancement (works without JS)

## Component Responsibilities

### FastAPI Application (`app/main.py`)

- Application initialization and configuration
- Middleware setup (sessions, CORS, security headers)
- Router registration
- Global error handlers
- Lifespan events (startup/shutdown)

### Routes (`app/routes/`)

- **overview.py**: Dashboard with server stats and recent activity
- **rooms.py**: CRUD operations for rooms, participant management
- **egress.py**: Start/stop recordings, list egress jobs
- **sip.py**: SIP trunk and call management (optional)
- **settings.py**: Display configuration and server info
- **sandbox.py**: Token generation and testing tools
- **auth.py**: Logout page

**Responsibilities:**
- Request parameter parsing
- Authentication/authorization enforcement
- Business logic orchestration
- Response formatting
- Error handling

### Services (`app/services/`)

- **livekit.py**: Wrapper around LiveKit SDK
  - Room operations (list, create, delete)
  - Participant operations (list, kick, mute)
  - Token generation
  - Egress management
  - SIP operations (if enabled)
  - Health checks

**Responsibilities:**
- Abstract LiveKit SDK complexity
- Provide clean interface for routes
- Handle SDK errors
- Measure SDK latency

### Security (`app/security/`)

- **basic_auth.py**: HTTP Basic Authentication
  - Credential verification with constant-time comparison
  - FastAPI dependency for route protection
  
- **csrf.py**: CSRF protection
  - Token generation using URLSafeTimedSerializer
  - Token validation
  - Integration with forms

**Responsibilities:**
- Enforce authentication on protected routes
- Prevent CSRF attacks
- Secure credential handling

### Templates (`app/templates/`)

- **base.html.j2**: Base layout with navigation, header, footer
- **Page templates**: Individual pages extending base
- **Partial templates**: Fragments for HTMX updates

**Responsibilities:**
- HTML structure and layout
- Data presentation
- HTMX integration
- Form generation with CSRF tokens

### Static Assets (`app/static/`)

- **CSS**: Custom styles extending Bootstrap
- **JavaScript**: Utility functions and HTMX helpers

**Responsibilities:**
- Visual styling
- Client-side interactivity
- Progressive enhancement

## Data Flow

### Read Operations (GET)

```
User Request → Auth Check → Route Handler → LiveKitClient
                                                  ↓
                                          LiveKit Server
                                                  ↓
User Response ← Template Render ← Route Handler ← SDK Response
```

### Write Operations (POST)

```
User Form Submit → Auth Check → CSRF Validation → Route Handler
                                                        ↓
                                                  LiveKitClient
                                                        ↓
                                                 LiveKit Server
                                                        ↓
User Redirect/Response ← Route Handler ← SDK Response
```

## Stateless Design

### No Persistence

- **No Database**: All data fetched from LiveKit on each request
- **No Redis**: No caching or session storage
- **No Background Workers**: No async tasks or job queues

### Session State

- **CSRF Tokens**: Stored in encrypted cookies via SessionMiddleware
- **Flash Messages**: Transient, stored in session for next request only
- **Authentication**: HTTP Basic Auth (browser handles credentials)

### Benefits

- **Simple Deployment**: No database setup or migrations
- **Horizontal Scaling**: Multiple instances without state sync
- **Always Fresh**: Data always current from LiveKit
- **Easy Backup**: No data to backup (LiveKit is source of truth)
- **Fault Tolerant**: Restart without data loss

### Trade-offs

- **No Historical Data**: Can't show trends or history
- **No Audit Log**: No record of who did what
- **SDK Latency**: Every request hits LiveKit API
- **Limited Caching**: Can't cache frequently accessed data

## Security Model

### Authentication

- **HTTP Basic Auth**: Simple, stateless, browser-supported
- **Single Admin Account**: From environment variables
- **Constant-Time Comparison**: Prevents timing attacks

### Authorization

- **All routes protected** except:
  - `/health` - Health check (for load balancers)
  - `/logout` - Logout information page

### CSRF Protection

- **Token Generation**: Per-request, time-limited
- **Form Integration**: Automatic via Jinja2 template function
- **Validation**: On all POST/PUT/DELETE requests

### Security Headers

- **HSTS**: Force HTTPS in production
- **CSP**: Content Security Policy (restrictive)
- **X-Frame-Options**: Prevent clickjacking
- **X-Content-Type-Options**: Prevent MIME sniffing
- **Referrer-Policy**: Control referrer information

### Secrets Management

- **Environment Variables**: All secrets from env
- **Never Logged**: API secrets never in logs
- **Masked in UI**: Only show first/last chars

## Deployment Options

### Standalone

```
Python + Uvicorn → LiveKit Server
```

### Docker

```
Docker Container → LiveKit Server
```

### Docker Compose

```
Docker Compose → Multiple Containers → LiveKit Server
```

### With Reverse Proxy (Recommended)

```
nginx/Caddy (TLS) → FastAPI Container → LiveKit Server
```

## Performance Considerations

### Request Latency

- **SDK Calls**: Directly impacts response time
- **No Caching**: Every request hits LiveKit
- **Mitigation**: Use fast network, minimize SDK calls per request

### Scalability

- **Stateless**: Horizontal scaling easy
- **LiveKit as Bottleneck**: SDK rate limits may apply
- **Mitigation**: Use reverse proxy caching for static assets

### Resource Usage

- **Memory**: Minimal (no caching, no persistence)
- **CPU**: Template rendering + SDK calls
- **Network**: Bandwidth to LiveKit server

## Technology Stack

### Backend

- **FastAPI**: Modern Python web framework
- **Jinja2**: Template engine
- **LiveKit SDK**: Official Python SDK
- **Uvicorn**: ASGI server

### Frontend

- **Bootstrap 5**: UI framework
- **HTMX**: Progressive enhancement
- **Bootstrap Icons**: Icon set
- **Vanilla JS**: Minimal custom JavaScript

### Development

- **Poetry**: Dependency management
- **pytest**: Testing framework
- **Black**: Code formatting
- **Ruff**: Fast linting
- **mypy**: Type checking

### Deployment

- **Docker**: Containerization
- **Docker Compose**: Local orchestration
- **Make**: Build automation

## Future Architecture Considerations

### Planned Enhancements

1. **WebSocket Support**
   - Real-time updates without polling
   - Push notifications from LiveKit

2. **Caching Layer** (Optional)
   - Redis for frequently accessed data
   - TTL-based invalidation
   - Trade stateless design for performance

3. **Background Workers** (Optional)
   - Async egress processing
   - Scheduled cleanup tasks
   - Requires job queue (Celery, RQ)

4. **Multi-User Support**
   - Database for user accounts
   - Role-based access control
   - Per-user preferences

5. **Audit Logging** (Optional)
   - Database for action logs
   - Compliance and security tracking
   - Who did what, when

### Architecture Evolution

The current stateless design is intentional for simplicity. Future versions may optionally add:

- **PostgreSQL**: User accounts, audit logs
- **Redis**: Caching, sessions
- **Celery**: Background tasks

While maintaining backward compatibility for stateless deployments.

## Conclusion

LiveKit Dashboard prioritizes simplicity and reliability through its stateless architecture. All data is sourced directly from LiveKit on each request, eliminating the complexity of data synchronization and persistence while ensuring data accuracy.

The SSR approach with progressive enhancement via HTMX provides a responsive user experience without heavy client-side frameworks, making the application lightweight and easy to maintain.

