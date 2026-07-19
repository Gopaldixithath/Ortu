# Agent API — chat assistant integration (`/api/agent/*`)

Server-to-server API that lets the ChatnCall AI assistant (webchat + WhatsApp)
look up a member's record and book / cancel / move classes on their behalf.
Implemented in `backend/app/routers/agent_api.py`; tests in
`backend/tests/test_agent_api.py`.

## Configuration

1. **Ortu side** — set a long random `ORTU_FITNESS_AGENT_KEY` in `.env`
   (blank = the whole `/api/agent/*` surface answers 503 and the assistant has
   no member abilities).
2. **ChatnCall side** — on the Ortu business, set the policy block (e.g. in
   `businesses.config_json.policy`):

   ```json
   "member_connector": {
     "base_url": "https://<ortu-site-host>",
     "agent_key": "<same ORTU_FITNESS_AGENT_KEY value>",
     "enabled": true
   }
   ```

   The fitness webchat/WhatsApp agent then runs the member flows in
   `app/industry/fitness/member_connector.py` (ChatnCall repo).

All requests carry `X-Ortu-Agent-Key: <key>`; wrong/missing key → 401.

## Security model

- **WhatsApp** — the sender's number is authenticated by the WhatsApp platform.
  `POST /member/identify {"phone": "<sender>"}` matches it against the mobile
  on the member record (same normalization as website phone login, UK 07… →
  +447…). No match → the assistant falls back to the email-code check.
- **Webchat** — anonymous visitors: `POST /member/verify/start {"email"}` sends
  the same 6-digit sign-in code used by website login (10-minute expiry,
  5-attempt limit, 5-codes-per-15-min rate limit); `POST /member/verify/check
  {"email","code"}` consumes it and returns the member context.
- These endpoints deliberately **never issue or rotate** the website's
  `membership_token`, so chat verification cannot log the member out of the
  site (and vice versa).

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/agent/classes?days=14` | Upcoming scheduled sessions with live remaining spaces |
| `POST /api/agent/member/identify` | `{phone}` → member context (WhatsApp path) |
| `POST /api/agent/member/verify/start` | `{email}` → emails 6-digit code (webchat path) |
| `POST /api/agent/member/verify/check` | `{email, code}` → member context |
| `GET /api/agent/member/{id}` | Refresh member context |
| `POST /api/agent/member/{id}/bookings` | `{session_id}` → book (same rules as the site: active membership, credits, capacity, not-started) |
| `POST /api/agent/member/{id}/bookings/{bid}/cancel` | Cancel (1-hour cutoff, restores credit) |
| `POST /api/agent/member/{id}/bookings/{bid}/move` | `{new_session_id}` → atomic reschedule; on failure the original booking is untouched |

**Member context** (returned by identify / verify/check / member detail and in
booking responses as `context`): `member` (id, name, email, phone,
approval_status), `membership` (plan, status, remaining_classes, `unlimited`,
period) or `null`, and `upcoming_bookings` (booking_id, class, coach, times,
`can_cancel`).

## Running the tests

```bash
cd backend
python -m unittest tests.test_agent_api    # 18 end-to-end tests on sqlite
```
