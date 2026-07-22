# Testing ORTU Fitness

Two automated layers, both run on every push/PR by
[`.github/workflows/test.yml`](../.github/workflows/test.yml):

| Layer | Tool | What it covers |
|---|---|---|
| **Backend** | `pytest` + in-memory SQLite + FastAPI `TestClient` | Every API endpoint and business rule: `/site`, signup + approval, all login modes, plan checkout + GoCardless completion, booking/cancel, admin dashboard, the GoCardless webhook, and the agent API. |
| **E2E** | `@playwright/test` (Chromium) | The real UI flows through the built SPA behind FastAPI: timetable, member signup, password login + cancel, booking, studio admin, and **mobile/responsive** (no horizontal scroll, on-screen webchat widget). |

### Scope note — the webchat bot is **not** tested here
The chat assistant's conversation logic lives in the separate ChatnCall platform
repo (`C:\ai-voice-platform`), so it cannot be exercised from this project. What
*is* tested here is the ORTU-side agent API (`/api/agent/*`) the bot calls
(`backend/tests/test_agent_api.py`). Do not expect this suite to catch
bot-phrasing regressions.

---

## Backend — `pytest`

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows: use py -3.11 -m venv .venv
pip install -r requirements-dev.txt
pytest -q                    # add --cov=app --cov-report=term-missing for coverage
```

Requires **Python 3.11** (matches Docker/CI). `requirements-dev.txt` adds
`pytest`, `pytest-cov` and `httpx` (needed by `TestClient`) on top of the runtime
deps.

**How it works** — [`tests/_harness.py`](../backend/tests/_harness.py) pins the
env and binds the app to a single in-memory SQLite engine *before* the app is
imported; [`tests/conftest.py`](../backend/tests/conftest.py) gives every test a
fresh schema, frozen naive-UTC time, small object factories
(`make_member`/`make_membership`/`make_session`/`make_booking`) and stubs for the
three external services (`stub_gocardless`, `capture_email`, `stub_twilio`). No
network, no real GoCardless/SMTP/Twilio, no Postgres.

> SQLite makes `.with_for_update()` row locks no-ops and bypasses Alembic
> (`create_all`), so true oversell-under-concurrency and migrations are not
> exercised. If needed later, add a Postgres-service CI job that runs
> `alembic upgrade head` for the booking/webhook tests.

## E2E — Playwright

```bash
# 1) build the SPA the backend will serve
npm --prefix frontend ci && npm --prefix frontend run build
# 2) install Playwright + Chromium (once)
cd e2e && npm ci && npx playwright install chromium
# 3) run — Playwright boots backend/scripts/e2e_server.py itself
npx playwright test
npx playwright show-report        # view the last run
```

On Windows, point Playwright at the 3.11 interpreter that has the backend deps:

```bash
E2E_PYTHON='C:\Customers\Ortu\backend\.venv\Scripts\python.exe' npx playwright test
```

[`backend/scripts/e2e_server.py`](../backend/scripts/e2e_server.py) serves the
built SPA against a throwaway SQLite DB seeded with a fixed timetable, one
approved member (`e2e@example.com` / `e2ePassword123`, unlimited plan, one
cancellable booking) and one pending member. GoCardless/SMTP/Twilio stay in
"setup mode" — the full payment + webhook paths are covered by pytest, so the
browser tests stop at the checkout boundary.

Because one seeded DB is shared for the whole run, tests run **serially with no
retries** (`playwright.config.js`); the specs are ordered so mutations don't
collide. The external ChatnCall webchat loader is blocked in `e2e/fixtures.js`
to keep runs deterministic.

## CI

`tests` workflow → two jobs: **backend** (pytest on SQLite, no services) and
**e2e** (build frontend → install deps → `npx playwright install --with-deps
chromium` → `npx playwright test`; `CI=true` makes Playwright start its own fresh
seeded server). A failing E2E run uploads the HTML report as an artifact.
