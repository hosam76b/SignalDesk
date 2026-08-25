# Testing

The Phase 1 and Phase 2 security suites use an isolated in-memory SQLite database and never connect to the configured application database.

Run the focused suites:

```powershell
.venv\Scripts\python.exe -m pytest test_phase1_schema.py test_phase2_security.py -q
```

Run with coverage reporting:

```powershell
.venv\Scripts\python.exe -m pytest test_phase1_schema.py test_phase2_security.py --cov=app --cov-report=term-missing
```