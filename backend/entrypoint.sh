#!/usr/bin/env sh
set -e

echo "[entrypoint] Waiting for the database to accept connections..."
python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
last = None
for _ in range(30):
    try:
        with create_engine(url).connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] Database is ready.")
        break
    except Exception as exc:  # noqa: BLE001
        last = exc
        time.sleep(2)
else:
    print(f"[entrypoint] Database not reachable: {last}", file=sys.stderr)
    sys.exit(1)
PY

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting ORTU Fitness on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
