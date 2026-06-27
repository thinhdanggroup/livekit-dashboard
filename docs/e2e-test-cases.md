# E2E Test Cases — LiveKit Dashboard

Playwright test cases for a future agent or human tester. All tests assume:
- App running at `http://localhost:8000`
- `.env` has `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=admin`, `ENABLE_SIP=true`
- A reachable LiveKit Cloud or self-hosted server configured in `.env`

---

## 0. Setup helpers

```js
// login — call at start of each test or use storageState
await page.goto('http://localhost:8000');
await page.waitForURL(/localhost:8000/);
// HTTP Basic Auth via URL
// or: pass { httpCredentials: { username: 'admin', password: 'admin' } } to browser.newContext()
```

---

## 1. Auth

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| AUTH-01 | Unauthenticated access redirects to 401 | `GET /rooms` with no credentials | 401 or Basic Auth challenge |
| AUTH-02 | Wrong password fails | Basic Auth with wrong password | 401 |
| AUTH-03 | Correct credentials succeed | Basic Auth with `admin:admin` then `GET /` | 200, overview page renders |
| AUTH-04 | Logout clears session | Navigate to `/logout`, then `GET /rooms` | 401 |

---

## 2. Overview

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| OV-01 | Overview page loads | `GET /` authenticated | Page renders, no 500 |
| OV-02 | Server status card visible | Look for status card | Contains "healthy" or error badge |
| OV-03 | SDK latency shown | Look for latency value | Number + "ms" visible |

---

## 3. Rooms

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| RM-01 | Rooms list loads | `GET /rooms` | Table or empty-state renders |
| RM-02 | Create room | Click "Create Room" → fill Name → submit | Room appears in list, flash success |
| RM-03 | Room name required | Submit create form with empty name | Browser validation blocks or server rejects |
| RM-04 | View room detail | Click eye icon on a room | Detail page loads with participant table |
| RM-05 | Edit room metadata | Click pencil icon → enter metadata JSON → save | Redirect to detail, metadata updated |
| RM-06 | Delete room | Click trash icon on a room → confirm | Room disappears from list |
| RM-07 | Generate join token | On detail page click "Generate Join Token" → fill identity → submit | Token returned as plain text |

### Participant management (requires an active room with participant)

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| PM-01 | Kick participant | Click kick button (person-x icon) → confirm | Participant disappears from list |
| PM-02 | Mute track | Click mic-mute icon → select track → choose "Mute" → Apply | Redirect back, track shows as muted |
| PM-03 | Unmute track | Same as PM-02 but choose "Unmute" | Track shown as unmuted |
| PM-04 | Update participant metadata | Click pencil icon on participant → enter JSON → Save | Redirect back |

---

## 4. Egress

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| EG-01 | Egress list loads | `GET /egress` | Page renders |
| EG-02 | Start room composite egress | Click "Start Egress" → type = Room Composite → fill room name + filename → Start | Flash success, job appears in list |
| EG-03 | Start track egress | Click "Start Egress" → type = Track → fill room, track SID, filename → Start | Flash or redirect; job created |
| EG-04 | Start web egress | Click "Start Egress" → type = Web → fill URL + filename → Start | Flash or redirect; job created |
| EG-05 | Stop active egress | Click "Stop" on an active egress → confirm | Job removed from active list |
| EG-06 | Type switcher shows correct form | In modal, change type dropdown | Correct form fields appear; others hidden |

---

## 5. Ingress

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| IN-01 | Ingress page loads | `GET /ingress` | Page renders, "Ingress Streams" heading visible |
| IN-02 | Create RTMP ingress | Click "Create Ingress" → type RTMP → fill name + room → Create | Flash success, item appears in table with RTMP badge |
| IN-03 | Create WHIP ingress | Same as IN-02 but type WHIP | Flash success, WHIP badge shown |
| IN-04 | Edit ingress | Click pencil icon → change name → Save | Flash success, new name in table |
| IN-05 | Delete ingress | Click trash icon → confirm in modal → Delete | Flash success, item removed |
| IN-06 | Copy URL/key button | Click clipboard icon on URL or stream key | Clipboard receives the value (check with `page.evaluate`) |

---

## 6. SIP Outbound Trunks (`ENABLE_SIP=true`)

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| SIP-OB-01 | Outbound page loads | `GET /sip-outbound` | Page renders |
| SIP-OB-02 | Create trunk (form) | Click "Create Outbound Trunk" → fill name, address, numbers → Create | Flash success, trunk in table |
| SIP-OB-03 | Edit trunk — all fields persist | Click edit on existing trunk → verify all 10 fields pre-filled | Name, address, transport, numbers, username, destination country, metadata, headers, headers_to_attributes all populated |
| SIP-OB-04 | Update trunk (form) | Edit modal → change name → Update | Flash success, updated name in table |
| SIP-OB-05 | Create trunk (JSON editor) | Switch to JSON tab → paste valid JSON → Create | Flash success, trunk created with JSON values |
| SIP-OB-06 | JSON editor overrides form fields | Fill form fields, then switch to JSON tab with different values → Create | JSON values used, not form values |
| SIP-OB-07 | Invalid JSON falls back to form | Paste invalid JSON in editor → Create | Flash success, form fields used |
| SIP-OB-08 | Delete trunk | Click delete → confirm | Flash success, trunk removed |

---

## 7. SIP Inbound Trunks

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| SIP-IB-01 | Inbound page loads | `GET /sip-inbound` | Page renders |
| SIP-IB-02 | Create inbound trunk | Click "Create Inbound Trunk" → fill name, numbers → Create | Flash success |
| SIP-IB-03 | Edit inbound trunk — all fields pre-filled | Click edit → verify 14 fields populated | name, numbers, allowed_addresses, auth_username, include_headers, ringing_timeout, max_call_duration all visible |
| SIP-IB-04 | Update inbound trunk | Change name → Update | Flash success |
| SIP-IB-05 | Delete inbound trunk | Delete → confirm | Flash success, removed |

---

## 8. SIP Dispatch Rules

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| SIP-DR-01 | Create dispatch rule (direct) | Click "Create Rule" → type Direct → fill room name → Create | Flash success, rule in table |
| SIP-DR-02 | Create dispatch rule (individual) | Type Individual → fill room prefix → Create | Flash success |
| SIP-DR-03 | Create rule via JSON editor | Switch to JSON tab → paste valid dispatch rule JSON → Create | Flash success |
| SIP-DR-04 | Edit dispatch rule | Click edit → change name → Update | Flash success |
| SIP-DR-05 | Delete dispatch rule | Delete → confirm | Flash success, removed |

---

## 9. Agents

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| AG-01 | Agents fleet page loads | `GET /agents` | Page renders |
| AG-02 | Agent detail page loads | Click on an agent name | Detail page with job breakdown chart renders |
| AG-03 | Dispatch agent | On detail page → "New dispatch" → fill room → Dispatch | Flash or redirect, dispatch appears in table |
| AG-04 | Delete dispatch | Click trash on a dispatch → confirm | Dispatch removed from table |

---

## 10. Homer SIP Monitor (`ENABLE_HOMER=true`)

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| HO-01 | Homer page loads | `GET /homer` | Search form renders |
| HO-02 | Search by Call-ID | Enter a known Call-ID → Search | Results table shows matching call |
| HO-03 | Call detail loads | Click a call-id in results | Detail page with 5 tabs (Flow, Messages, Session Info, Logs, Export) |
| HO-04 | Flow tab ladder diagram | Click Flow tab | SIP arrows rendered with timestamps |
| HO-05 | Export JSON | Click Export tab → download | Browser downloads a `.json` file |

---

## 11. Settings & Sandbox

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| SET-01 | Settings page loads | `GET /settings` | Config cards render, secrets masked |
| SB-01 | Token generator loads | `GET /sandbox` | Form renders |
| SB-02 | Generate token | Fill room + identity → Generate | Token appears in output field |
| SB-03 | Copy token to clipboard | Click copy button | Clipboard has token value |

---

## 12. Security

| ID | Description | Steps | Expected |
|----|-------------|-------|----------|
| SEC-01 | CSRF on room create | POST `/rooms` without `csrf_token` | Reject (redirect with error or 400) |
| SEC-02 | CSRF on room delete | POST `/rooms/x/delete` without valid token | Reject |
| SEC-03 | CSRF on egress start | POST `/egress/start` without token | Reject |
| SEC-04 | CSRF on ingress create | POST `/ingress/create` without token | Reject |
| SEC-05 | Security headers present | Check response headers on any page | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` present |

---

## Playwright setup snippet

```js
import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:8000';
const CTX = { httpCredentials: { username: 'admin', password: 'admin' } };

test.use(CTX);

test('RM-02 create room', async ({ page }) => {
  await page.goto(`${BASE}/rooms`);
  await page.click('button[data-bs-target="#createRoomModal"]');
  await page.fill('#name', `e2e-test-${Date.now()}`);
  await page.click('#createRoomModal button[type="submit"]');
  await expect(page.locator('.alert-success')).toBeVisible({ timeout: 5000 });
});
```
