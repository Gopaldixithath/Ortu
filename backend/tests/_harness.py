"""Shared test harness — a single in-memory SQLite engine bound to the app.

Imported first by ``conftest.py`` (and by ``test_agent_api.py``) so that every
test module shares exactly one engine. This module MUST run before ``app.db``
is imported, because ``app.db`` raises if ``DATABASE_URL`` is unset and binds
its engine at import time.

``app.db`` also calls ``load_dotenv()`` on import, which would otherwise pull
SMTP/Twilio/admin values out of the local ``.env`` and make ``is_configured()``
return True in tests. We therefore pin every externally-configurable variable
to a known value up-front; ``load_dotenv(override=False)`` then leaves them
alone (it only fills keys that are absent from ``os.environ``).
"""

from __future__ import annotations

import os
from datetime import datetime

# --- environment: pin BEFORE importing the app -------------------------------
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ORTU_FITNESS_AGENT_KEY"] = "test-agent-key"
os.environ["ORTU_FITNESS_ADMIN_KEY"] = "test-admin-key"
os.environ["GOCARDLESS_ENVIRONMENT"] = "sandbox"
# Force every external integration to "not configured"; individual tests opt in
# by patching the relevant ``is_configured`` / ``send`` (see conftest fixtures).
for _var in (
    "GOCARDLESS_ACCESS_TOKEN",
    "GOCARDLESS_WEBHOOK_ENDPOINT_SECRET",
    "SMTP_HOST",
    "SMTP_FROM",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_VERIFY_SERVICE_SID",
    "ORTU_FITNESS_PUBLIC_URL",
):
    os.environ[_var] = ""

from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


# SQLite only autoincrements INTEGER primary keys; render BigInteger as INTEGER.
@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN201
    return "INTEGER"


import app.db as app_db  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402

# One shared in-memory database for every thread the TestClient uses.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
app_db.engine = engine
SessionLocal.configure(bind=engine)

import app.models  # noqa: E402,F401  (register tables on Base.metadata)
from app.main import app  # noqa: E402

AGENT_KEY = os.environ["ORTU_FITNESS_AGENT_KEY"]
ADMIN_KEY = os.environ["ORTU_FITNESS_ADMIN_KEY"]
AGENT_HEADERS = {"X-Ortu-Agent-Key": AGENT_KEY}
ADMIN_HEADERS = {"X-Ortu-Admin-Key": ADMIN_KEY}
BUSINESS_KEY = "ortu-fitness"


def naive_utc_now() -> datetime:
    """SQLite returns naive datetimes, so tests freeze 'now' to naive UTC."""
    return datetime.utcnow()


def reset_db() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
