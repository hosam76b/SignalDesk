# GitHub update workflow

## Development machine

1. Make the code change locally.
2. Run the relevant tests, then run the full suite with `python -m pytest -q`.
3. Run the frontend build with `npm.cmd run build` from `frontend` when frontend files changed.
4. Commit and push to `main`.

Every push to `main` runs `.github/workflows/ci.yml`. The workflow runs the backend tests, builds the frontend, and publishes a 30-day ZIP artifact for that commit. Pull requests run the tests and frontend build but do not publish a package.

## External Windows installation

Run PowerShell as Administrator from the installation directory:

```powershell
.\deployment\update-from-github.ps1
```

The updater refuses to overwrite local changes, fast-forwards from `origin/main`, installs Python dependencies, runs the backend tests, builds the frontend, and restarts `SignalDeskServer` only after all checks pass. It preserves `.env`, the local database, uploaded media, and local knowledge files.

To use another repository or branch:

```powershell
.\deployment\update-from-github.ps1 -Repository "https://github.com/OWNER/REPOSITORY.git" -Branch main
```

The external machine must have Git, Python, Node.js/npm, an existing virtual environment, and the `SignalDeskServer` Windows service installed. GitHub Actions cannot directly update an external machine without credentials and a deployment agent; the updater is the controlled deployment step for those machines.