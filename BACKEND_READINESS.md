# Backend Readiness

## Tests

Run the complete deterministic suite:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Run with coverage:

```powershell
.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

External APIs are mocked in `tests/test_services.py`; no Apify, YouTube, RSS, or browser credentials are required.

## Migrations

Set `DB_URL` or update the environment configuration, then run:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

Check the current revision:

```powershell
.venv\Scripts\python.exe -m alembic current
```

The baseline revision is `0001_topic_centric_schema`.

## Seed Data

The seed operation is idempotent and creates the default super admin, General Monitoring topic, assignment, RSS sample, and Apify sample:

```powershell
.venv\Scripts\python.exe seed.py
```

Default development login: `admin@example.com` / `admin123`. Change it before production use.

## OpenAPI

Swagger UI is available at `/docs`. Export a frontend-consumable JSON document with:

```powershell
.venv\Scripts\python.exe export_openapi.py
```

This writes `openapi.json` at the repository root.
