## 🧩 Rewritten Prompt (C.R.A.F.T.E.D)

**Context**
Build a **stateless**, self-hosted, server-side rendered (SSR) **FastAPI + Jinja2** dashboard to manage a private **LiveKit** server using the **LiveKit Python SDK** only. No database, no Redis, no background workers, no audit log, no API key/token manager, and no OAuth/OIDC. Authentication is **one fixed admin account** (username/password from env). The app reads LiveKit connection details from env and issues SDK calls directly on each request.

**Role**
Act as a senior full-stack engineer. Produce a minimal yet solid, production-deployable FastAPI/Jinja2 codebase with clear structure, security basics, and exact examples that can be extended later.

**Action**
Design and implement the following:

- **Features (SDK-driven, no persistence):**

  - **Overview/Health:** current rooms count, participants, basic node status, recent errors (in-memory only), SDK latency.
  - **Rooms:** list/search/filter; create/close room; view metadata; generate **join tokens** (on-the-fly, never stored); copy-to-clipboard.
  - **Participants:** per-room view with tracks, bitrate, RTT/jitter/packet loss; force mute/kick; toggle track publish/subscribe where supported.
  - **Egress/Recordings:** start/stop composite/file egress; list **current** egress jobs via SDK; present download URLs if returned.
  - **Webhooks sandbox (optional):** show sample payloads + HMAC verification helper; no storage.
  - **SIP/Telephony (feature flag):** read trunks, dispatch rules, call rooms; basic create/delete if the SDK exposes it.
  - **Settings (read-only config):** LiveKit URL, server version (if queriable).
  - **Help/Sandbox:** quick token generator page for testing joins (generated on demand).

- **Architecture (stateless):**

  - FastAPI app with **Jinja2 SSR** templates; optional **HTMX** for progressive enhancement & interval polling (`hx-get` with `hx-trigger="every 5s"`).
  - **HTTP Basic Auth** with one admin user (env: `ADMIN_USERNAME`, `ADMIN_PASSWORD`). Use HTTPS in production and secure headers.
  - **LiveKitClient** wrapper reading `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
  - **No DB**: any transient data (flash messages, temporary errors) lives in memory per-process.
  - **Packaging**: Dockerfile (multi-stage) + minimal `docker-compose.yml` for local dev (app only).

- **Pages & Routes (SSR):**

  - `/` Overview (rooms/participants totals, node status).
  - `/rooms` list with search/pagination; POST actions: create/close.
  - `/rooms/{name}` detail with participants, tracks, buttons: generate join token, mute/kick.
  - `/egress` list current jobs; POST start/stop egress (composite/file).
  - `/sip-outbound` list/create SIP outbound calls.
  - `/sip-inbound` list/create SIP inbound calls.
  - `/settings` read-only env/config info.
  - Auth: `/auth/login` (HTTP Basic challenge) and `/logout` (clears auth header hint page).

- **Security (simple but safe):**

  - HTTP Basic Auth (starlette `HTTPBasic`); rate-limit optional (simple in-memory).
  - CSRF tokens for POST forms; secure cookies only used for flash/CSRF (stateless regarding data).
  - Security headers: HSTS, CSP (strict), X-Frame-Options, Referrer-Policy; gzip & caching disabled for HTML.
  - Never log API secrets; show **only** masked values in UI.

- **Deliverables:**

  - Minimal architecture note; `.env.example`.
  - Project tree with FastAPI app, templates, and `services/livekit.py`.
  - Code stubs/snippets for:

    - `LiveKitClient` (`list_rooms`, `generate_token`, `start_composite_egress`).
    - `routes/rooms.py` (GET list + POST close).
    - `templates/rooms/index.html.j2` table with HTMX polling.
    - Optional WebSocket endpoint streaming room updates.
    - Simple `security/basic_auth.py` and CSRF helper.

  - Dockerfile + compose; Makefile with `run`, `fmt`, `lint`.
  - Short README with setup/run steps.

**Format**
Return:

1. brief overview;
2. architecture note;
3. requirements & routes;
4. project tree;
5. concrete code snippets;
6. setup/run instructions;
7. a **Definition of Done** checklist tailored to stateless scope.

**Tone**
Pragmatic, concise, implementation-oriented.

**Examples**
Include these minimal, runnable snippets:

```python
# services/livekit.py
import os, time
from livekit import api

class LiveKitClient:
    def __init__(self):
        self.url = os.environ["LIVEKIT_URL"]
        self.key = os.environ["LIVEKIT_API_KEY"]
        self.secret = os.environ["LIVEKIT_API_SECRET"]
        self.room = api.RoomServiceClient(self.url, self.key, self.secret)
        self.egress = api.EgressServiceClient(self.url, self.key, self.secret)

    def list_rooms(self):
        t0 = time.perf_counter()
        resp = self.room.list_rooms()
        return resp.rooms, (time.perf_counter() - t0)

    def generate_token(self, room, identity, name=None, ttl=3600, metadata=""):
        grant = api.AccessToken(self.key, self.secret).with_identity(identity).with_name(name or identity)
        grant.add_grant(api.VideoGrant(room_join=True, room=room))
        return grant.to_jwt(ttl=ttl)

    def start_composite_egress(self, room, file_path):
        req = api.StartEgressRequest(composite=api.CompositeEgressRequest(room_name=room, file=api.EncodedFileOutput(file_path=file_path)))
        return self.egress.start_egress(req)

    def stop_egress(self, egress_id):
        return self.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
```

```python
# routes/rooms.py
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from services.livekit import LiveKitClient
from security.basic_auth import requires_admin

router = APIRouter()

@router.get("/rooms", dependencies=[Depends(requires_admin)])
def rooms_index(request: Request, lk: LiveKitClient = Depends(LiveKitClient)):
    rooms, latency = lk.list_rooms()
    return request.app.templates.TemplateResponse("rooms/index.html.j2", {"request": request, "rooms": rooms, "latency": latency})

@router.post("/rooms/{name}/close", dependencies=[Depends(requires_admin)])
def rooms_close(name: str, lk: LiveKitClient = Depends(LiveKitClient)):
    lk.room.delete_room(api.DeleteRoomRequest(room=name))
    return RedirectResponse(url="/rooms", status_code=303)
```

```html
{# templates/rooms/index.html.j2 #} {% extends "base.html.j2" %} {% block
content %}
<h1 class="mb-2">Rooms <small class="text-muted">(updated every 5s)</small></h1>
<div hx-get="/rooms" hx-trigger="every 5s" hx-swap="outerHTML">
  <table class="table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Participants</th>
        <th>Created</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {% for r in rooms %}
      <tr>
        <td><a href="/rooms/{{ r.name }}">{{ r.name }}</a></td>
        <td>{{ r.num_participants }}</td>
        <td>{{ r.creation_time }}</td>
        <td>
          <form method="post" action="/rooms/{{ r.name }}/close">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
            <button class="btn btn-danger btn-sm">Close</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

```python
# security/basic_auth.py
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

basic = HTTPBasic()

def requires_admin(creds: HTTPBasicCredentials = Depends(basic)):
    if creds.username == os.environ.get("ADMIN_USERNAME") and creds.password == os.environ.get("ADMIN_PASSWORD"):
        return True
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})
```

```python
# main.py (sketch)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routes import rooms, sip_outbound, sip_inbound, settings

app = FastAPI()
app.templates = Jinja2Templates("templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(rooms.router)
# ... include other routers
```

**Definition of Done**

- App is stateless: no DB/Redis/background workers; all data fetched directly from LiveKit per request.
- HTTP Basic Auth using one admin account from env; all routes protected.
- `/`, `/rooms`, `/rooms/{name}`, `/sip-outbound`, `/sip-inbound`, `/settings` render via SSR and perform listed actions through SDK.
- Docker image builds and runs with `.env` (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`).
- Secrets never shown in full; secure headers enabled; CSRF on POST forms.
