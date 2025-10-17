# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- WebSocket live updates for real-time room/participant changes
- Advanced participant management features
- Recording download management
- Multi-user support with role-based access control
- Ingress management
- Analytics and metrics dashboard
- Dark mode theme
- Mobile-responsive improvements

## [0.1.0] - 2025-01-XX

### Added

- Initial release of LiveKit Dashboard
- **Overview Dashboard**
  - Server status monitoring
  - Active rooms and participants count
  - SDK latency tracking
  - Recent rooms list
- **Room Management**
  - List all active rooms
  - Create new rooms with custom settings
  - View room details and metadata
  - Close/delete rooms
  - Search and filter rooms
- **Participant Management**
  - View participants in rooms
  - See participant tracks (audio/video)
  - Kick participants from rooms
  - View participant metadata
- **Token Generation**
  - Generate join tokens on-the-fly
  - Customize token permissions (publish, subscribe, data)
  - Set token TTL and metadata
  - Copy tokens to clipboard
  - Quick test links for LiveKit Meet
- **Egress/Recording**
  - List active egress jobs
  - Start room composite egress
  - Stop egress jobs
  - View file outputs and download URLs
  - Support for different layouts (grid, speaker)
  - Audio-only and video-only options
- **SIP Integration** (Optional)
  - View SIP trunks
  - Create outbound SIP calls
  - View inbound dispatch rules
  - Room-to-phone bridge management
- **Settings**
  - View LiveKit server configuration
  - Display masked API credentials
  - Feature flags status
  - Security settings overview
- **Sandbox/Testing**
  - Token generator with full customization
  - HMAC webhook verification helper
  - Quick test URL generation
- **Security**
  - HTTP Basic Authentication
  - CSRF protection on all POST forms
  - Security headers (HSTS, CSP, X-Frame-Options, etc.)
  - Constant-time credential comparison
  - Never log or display full API secrets
- **Architecture**
  - Stateless SSR with FastAPI + Jinja2
  - No database or Redis required
  - HTMX for progressive enhancement and auto-refresh
  - Docker support with multi-stage build
  - Health check endpoint
  - Comprehensive error handling
- **Developer Experience**
  - Makefile with common commands
  - Docker Compose for local development
  - Poetry for dependency management
  - pytest test suite
  - Black code formatting
  - Ruff linting
  - Type hints with mypy
  - Comprehensive documentation
  - Setup script for quick start

### Security

- All routes require authentication except `/health` and `/logout`
- CSRF tokens on all state-changing operations
- Secure password comparison using `secrets.compare_digest`
- Security headers on all responses
- API secrets never exposed in full in UI

### Documentation

- Comprehensive README with setup instructions
- Docker deployment guide
- Contributing guidelines
- API endpoint documentation
- Security best practices
- Environment variable reference

## Release Notes

### v0.1.0 - Initial Release

This is the first release of LiveKit Dashboard, a stateless, self-hosted management interface for LiveKit servers.

**Key Features:**

- Complete room and participant management
- Token generation and testing tools
- Egress recording capabilities
- Optional SIP integration
- Secure by default with HTTP Basic Auth
- Zero-dependency architecture (no DB/Redis)
- Docker-ready deployment

**Installation:**

```bash
git clone <repository-url>
cd livekit-dashboard
make setup
make dev
```

**Requirements:**

- Python 3.10+
- LiveKit server instance
- LiveKit API credentials

For detailed setup instructions, see [README.md](README.md).

---

## Version History

- **0.1.0** (2025-01-XX) - Initial release
