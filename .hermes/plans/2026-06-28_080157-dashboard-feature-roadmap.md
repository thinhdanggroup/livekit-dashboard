# Dashboard Feature Roadmap Implementation Plan

> **For Hermes:** Use Claude Code CLI to implement this plan task-by-task, one feature slice at a time, with verification after each slice.

**Goal:** Build the full dashboard feature set we discussed, starting with shared foundations and then shipping operator workflows, observability, management actions, and UX polish.

**Architecture:**
- Keep the existing FastAPI/Jinja2 app structure and add new routes/components incrementally.
- Prefer shared UI primitives and reusable data-loading helpers so search, filters, charts, and live panels do not drift apart.
- Use Claude CLI for each implementation slice: inspect, edit, test, then verify with git/test output before moving on.

**Tech Stack:** FastAPI, Jinja2 templates, HTMX/Bootstrap, existing LiveKit client layer, pytest.

---

## Task list

### Phase 0 — Project scaffolding and execution workflow

- [ ] **Task 0.1: Map the current dashboard surface area**
  - Inspect `app/main.py`, `app/routes/*.py`, `app/templates/*.j2`, `app/static/*`, and `tests/*`.
  - Identify which features already exist versus which need new routes, template partials, or API helpers.
  - Output a short inventory before coding.

- [ ] **Task 0.2: Define the Claude CLI execution contract**
  - Decide the per-task Claude prompt format, allowed tools, and verification commands.
  - Standardize the pattern: inspect → implement → test → review → commit.
  - Save the exact Claude prompt template in the plan notes so every later task uses the same workflow.

- [ ] **Task 0.3: Create a feature backlog file if needed**
  - If the roadmap needs a separate checklist file for execution, add one under `.hermes/plans/` or `.hermes/` and keep this roadmap as the source of truth.
  - File should track task status, owner, and verification result.

### Phase 1 — Shared foundations

- [ ] **Task 1.1: Add a reusable dashboard data layer**
  - Create or extend a service module for common dashboard queries, response shaping, and empty-state defaults.
  - Likely files: `app/services/dashboard.py` or similar; tests in `tests/test_dashboard_service.py`.

- [ ] **Task 1.2: Add shared filter state handling**
  - Support date range, search query, sort order, and live-refresh flags in a single parsed state object.
  - Likely files: `app/utils/filters.py`, shared helper tests.

- [ ] **Task 1.3: Add common UI partials**
  - Extract reusable cards, empty states, badges, tables, and action menus into partial templates.
  - Likely files: `app/templates/partials/*.j2`.

- [ ] **Task 1.4: Add chart/data formatting helpers**
  - Add helpers for sparklines, percent formatting, duration formatting, and status colors.
  - Likely files: `app/main.py` filters or `app/utils/formatters.py`.

### Phase 2 — Global search and dashboard navigation

- [ ] **Task 2.1: Implement global search endpoint**
  - Search across rooms, agents, participants, egress, ingress, SIP, and recent incidents.
  - Likely files: `app/routes/search.py`, templates for results.

- [ ] **Task 2.2: Add search UI to the top bar**
  - Add keyboard-accessible search input and results dropdown/modal.
  - Likely files: `app/templates/base.html.j2`, shared partials.

- [ ] **Task 2.3: Add keyboard shortcuts**
  - Include shortcuts for search, refresh, and quick navigation between major sections.
  - Likely files: `app/static/js/dashboard.js`, template wiring.

- [ ] **Task 2.4: Improve breadcrumbs and sticky headers**
  - Make deep pages easier to navigate and identify.
  - Likely files: `app/templates/base.html.j2`, section templates.

### Phase 3 — Time-range filters, auto-refresh, and exports

- [ ] **Task 3.1: Add global time-range controls**
  - Support last 15m / 1h / 24h / 7d and custom dates.
  - Likely files: shared filter UI and dashboard endpoints.

- [ ] **Task 3.2: Add auto-refresh toggle**
  - Make refresh interval configurable and persist the preference.
  - Likely files: template controls + JS.

- [ ] **Task 3.3: Add export actions**
  - Export visible metrics, room lists, and incident data as CSV/JSON.
  - Likely files: `app/routes/exports.py` or route extensions, tests for payloads.

- [ ] **Task 3.4: Add copy-to-clipboard actions**
  - Add copy buttons for IDs, URLs, and tokens where appropriate.
  - Likely files: shared action partial and JS utility.

### Phase 4 — Health overview and incident visibility

- [ ] **Task 4.1: Build a health overview panel**
  - Surface API health, LiveKit health, SIP state, egress/ingress state, and last refresh timestamp.
  - Likely files: `app/routes/overview.py`, overview template.

- [ ] **Task 4.2: Add an incident/error feed**
  - Show recent failures, warnings, reconnects, and auth errors with severity and timestamps.
  - Likely files: `app/routes/incidents.py`, dashboard data helper, tests.

- [ ] **Task 4.3: Add quality charts**
  - Add latency, jitter, packet loss, and connection-success trends.
  - Likely files: new chart partials, data shaping helpers.

- [ ] **Task 4.4: Add a connection funnel**
  - Show attempts → joins → active sessions → drops.
  - Likely files: overview cards and chart data.

### Phase 5 — Room and participant operations

- [ ] **Task 5.1: Build live room detail view**
  - Show participants, tracks, publish/subscription state, metadata, and recent events in one page.
  - Likely files: `app/routes/rooms.py`, room detail templates.

- [ ] **Task 5.2: Add participant actions**
  - Support mute/unmute, disconnect, unpublish, and annotation/note actions.
  - Likely files: `app/routes/rooms.py` or a new actions route, form/HTMX handlers.

- [ ] **Task 5.3: Add room lifecycle timeline**
  - Display joins, leaves, track changes, and media changes chronologically.
  - Likely files: room detail partials and timeline data helper.

- [ ] **Task 5.4: Add pinned rooms**
  - Allow users to pin important rooms for quick access.
  - Likely files: persistence helper and room list UI.

- [ ] **Task 5.5: Add room notes and tags**
  - Let operators tag rooms (prod/demo/support/VIP) and add short notes.
  - Likely files: metadata storage helpers, edit modal, tests.

### Phase 6 — Saved views, alerts, and reports

- [ ] **Task 6.1: Add saved dashboard views**
  - Persist common combinations of filters, visible panels, and sort order.
  - Likely files: `app/routes/views.py` or settings storage, template controls.

- [ ] **Task 6.2: Add alert rules**
  - Create thresholds for room spikes, participant drops, egress failures, and SIP outages.
  - Likely files: `app/routes/alerts.py`, persistence layer, tests.

- [ ] **Task 6.3: Add notifications delivery hooks**
  - Wire alerts to the existing notification channels used by the project, or create a simple webhook/email hook if needed.
  - Likely files: integration helpers, docs, tests.

- [ ] **Task 6.4: Add scheduled summary reports**
  - Generate daily/weekly dashboard summaries and operator digests.
  - Likely files: report generation route or background job integration.

### Phase 7 — Diagnostics and support tooling

- [ ] **Task 7.1: Add one-click diagnostics**
  - Create a support bundle for a room, participant, or failed request.
  - Likely files: `app/routes/diagnostics.py`, archive/export helpers.

- [ ] **Task 7.2: Add webhook tester/simulator**
  - Validate integration payloads without needing real production traffic.
  - Likely files: `app/routes/webhooks.py` or admin tools page.

- [ ] **Task 7.3: Add audit log visibility**
  - Show recent operator actions and config changes.
  - Likely files: events storage, admin page, tests.

### Phase 8 — UX polish and accessibility

- [ ] **Task 8.1: Add theme support**
  - Support dark/light/system theme switching.
  - Likely files: `app/templates/base.html.j2`, JS, local storage preference.

- [ ] **Task 8.2: Make layouts responsive**
  - Tune sidebar, tables, cards, and modals for mobile and tablet widths.
  - Likely files: `app/static/css/style.css`, templates.

- [ ] **Task 8.3: Add richer chart visuals**
  - Use sparklines and compact trend indicators where full charts are unnecessary.
  - Likely files: shared chart partials.

- [ ] **Task 8.4: Improve empty states everywhere**
  - Replace blank sections with context-specific guidance and next actions.
  - Likely files: all major section templates.

### Phase 9 — Real-time and advanced features

- [ ] **Task 9.1: Add a live event stream**
  - Stream new room/participant/egress events in near real time.
  - Likely files: events route, HTMX/SSE/WebSocket plumbing.

- [ ] **Task 9.2: Add anomaly detection heuristics**
  - Flag unusual disconnect spikes, failed joins, and degraded media quality.
  - Likely files: analytics helper and incident feed integration.

- [ ] **Task 9.3: Add session replay metadata**
  - Let operators inspect key historical events for a past session.
  - Likely files: room/session history route.

- [ ] **Task 9.4: Add role-based views**
  - Tailor visibility and actions for admin, support, and read-only users.
  - Likely files: auth/permission helpers and template guards.

### Phase 10 — Testing, cleanup, and release

- [ ] **Task 10.1: Add/expand tests for each new route and helper**
  - Cover new search, filters, exports, alerts, actions, and timeline behavior.
  - Likely files: `tests/test_*.py` new and existing.

- [ ] **Task 10.2: Run the full test suite and fix regressions**
  - Use the project’s test command and record failures/fixes per phase.

- [ ] **Task 10.3: Review templates and static assets for duplication**
  - Remove one-off code paths once shared partials are stable.

- [ ] **Task 10.4: Final Claude CLI pass**
  - Run Claude Code in read-only review mode on the final diff for quality, missing cases, and polish suggestions.

- [ ] **Task 10.5: Commit and push the finished roadmap work**
  - Only after all tests pass and the diff is reviewed.

---

## Claude CLI execution template

Use this prompt shape for each implementation slice:

```text
You are working in /home/thinhda/Documents/codes/livekit-dashboard.
Task: implement <task name from the roadmap>.

Requirements:
- Inspect the repository before editing.
- Make the smallest correct change for this slice.
- Add or update tests.
- Run the relevant tests.
- Report changed files, commands run, and verification results.
- Do not commit or push unless explicitly instructed for that slice.
```

## Suggested implementation order

1. Shared foundations
2. Search + navigation
3. Time filters + refresh + exports
4. Health + incidents + charts
5. Room/participant management
6. Saved views + alerts + reports
7. Diagnostics + webhook tester
8. Theme + accessibility polish
9. Live event stream + advanced analytics
10. Full test pass + final review

## Risks / tradeoffs

- Some features may require persistence that the current app does not yet have.
- Realtime streams and anomaly detection may need backend support rather than only template changes.
- Role-based views depend on the current auth model; confirm it before overbuilding permissions.
- Keep the first pass simple and ship one usable slice at a time.
