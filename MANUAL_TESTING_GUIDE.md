# Manual Testing Guide

This guide covers the currently implemented local UI and API workflows. It intentionally marks unavailable UI features instead of treating navigation placeholders as working functionality.

## 1. Launch

Open two PowerShell terminals from the repository root.

### Backend

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --ws none
```

Check:

- `http://127.0.0.1:8000/health` returns `200`.
- `http://127.0.0.1:8000/docs` opens Swagger UI.
- `http://127.0.0.1:8000/api/scraper/health` returns `200`.

### Frontend

```powershell
Push-Location frontend
npm run dev -- --hostname=127.0.0.1 --port=3000
Pop-Location
```

Open `http://localhost:3000`. Use `localhost`, not `127.0.0.1`, when testing the Next.js development page.

### Seed data

Run from a third terminal:

```powershell
.venv\Scripts\python.exe seed.py
```

The seed is idempotent. It creates the default topic, two additional topics, scoped sources and keywords, sample posts, and Apify actor configuration records.

## 2. Test Accounts

| Persona | Email | Password | Expected access |
|---|---|---|---|
| SuperAdmin | `admin@example.com` | `admin123` | Global API access |
| TopicAdmin | `topic-admin@example.com` | `topicadmin123` | Assigned Child Safety topic management |
| Monitor | `monitor@example.com` | `monitor123` | Assigned topic read access |

These are development credentials only. Do not use them in production.

## 3. Auth and Session

- [ ] Open the frontend and confirm the login screen loads without console errors.
- [ ] Login as SuperAdmin; confirm the dashboard appears.
- [ ] Confirm `/api/auth/login` returns `200` and a bearer token.
- [ ] Confirm dashboard cards load from `/api/dashboard/stats` and `/api/dashboard/recent-activity`.
- [ ] Refresh the page; confirm the session remains active through `localStorage` key `signaldesk_token`.
- [ ] Click Sign out; confirm the token is removed and the login screen returns.
- [ ] Try a wrong password; confirm the login error is displayed.
- [ ] Submit malformed credentials; confirm the UI handles `401` without a blank page.
- [ ] Password reset UI: **Not implemented**. The current UI has no password-reset route or form.

## 4. Topics and Navigation

Use Swagger or browser DevTools to call the topic endpoints while the UI is open.

- [ ] As SuperAdmin, `GET /api/v1/topics` lists General Monitoring, Child Safety Monitoring, and Public Health Signals.
- [ ] As TopicAdmin, `GET /api/v1/topics` lists only Child Safety Monitoring.
- [ ] As Monitor, `GET /api/v1/topics` lists only the assigned topic.
- [ ] In Management, switch the topic selector and confirm sources/keywords reload from the selected topic.
- [ ] Create/edit topics as SuperAdmin: **API-supported; no topic create/edit UI is currently implemented.**
- [ ] Attempt an unassigned topic request as TopicAdmin/Monitor; expect `403`.

## 5. Dashboard

- [ ] Confirm total posts, flagged posts, RSS posts, and severity cards display values.
- [ ] Confirm platform distribution renders without a JavaScript error.
- [ ] Confirm recent activity renders and pagination controls work.
- [ ] Topic-specific dashboard filtering: **Not implemented in the current dashboard UI.** Use `/api/v1/topics/{topic_id}/stats` for topic-scoped stats.
- [ ] Active/pending/failed scraper status widget: **Not implemented in the current UI.** Use `/api/scraper/status` and source `status` fields.
- [ ] Real-time alerts: **Not implemented.**

## 6. Sources and Apify

Login as SuperAdmin or TopicAdmin, open `Sources & keywords`, and select `Child Safety Monitoring`.

- [ ] Confirm seeded sources display with `active` status.
- [ ] Add an RSS source using `https://example.com/manual-feed.xml`; expect the item to appear with `active` status.
- [ ] Add an Apify source with actor ID `apify/facebook-posts-scraper`; confirm the request payload includes `target_type: url` and `apify_actor_id`.
- [ ] Edit a source; confirm the UI sends `PUT /api/v1/topics/{topic_id}/sources/{source_id}`.
- [ ] Delete a source; confirm the UI sends `DELETE` and removes the row.
- [ ] Toggle source status: **Backend endpoint exists at `PATCH /api/v1/topics/{topic_id}/sources/{source_id}/toggle`, but no toggle control is currently present in the UI.**
- [ ] Cross-topic source access as TopicAdmin; expect `403`.
- [ ] Monitor source creation/update/delete; expect `403`.
- [ ] Trigger scraper from UI: **No scraper trigger control is currently present.** API smoke test: `POST /api/scraper/trigger?topic_id={topic_id}` as SuperAdmin only. Avoid real Apify/network jobs during manual testing unless explicitly intended.

## 7. Keywords

- [ ] Switch to Keywords and confirm only the selected topic's keywords appear.
- [ ] Add a keyword; confirm `POST /api/v1/topics/{topic_id}/keywords` succeeds.
- [ ] Edit a keyword; confirm `PUT` is used.
- [ ] Delete a keyword; confirm `DELETE` is used.
- [ ] Monitor keyword mutations; expect `403`.

## 8. News/Post Viewer

- [ ] Open Intelligence Feed and confirm `/api/data/posts/latest?limit=500` succeeds.
- [ ] Search by title, content, author, and platform.
- [ ] Test time-range filters and pagination.
- [ ] Open a post and confirm content, media, and original URL render.
- [ ] Topic-filtered news: **The current Feed uses the global latest-post endpoint.** Use `/api/v1/topics/{topic_id}/news` to verify strict topic filtering.
- [ ] AI analysis details modal: **Not implemented in the current Feed UI.**

## 9. User Management and Roles

- [ ] SuperAdmin can use `/api/users` to create users and assign roles.
- [ ] Assign TopicAdmin/Monitor through `POST /api/v1/topics/{topic_id}/assign-user`.
- [ ] Confirm TopicAdmin cannot assign another TopicAdmin; expect `403`.
- [ ] Confirm Monitor cannot change roles; expect `403`.
- [ ] User-management screen: **Not implemented in the current UI.** Use Swagger for this workflow.

## 10. Error and Network Monitoring

In Chrome/Edge DevTools:

1. Open **Network**, enable **Preserve log**, and filter by `Fetch/XHR`.
2. Inspect each request URL, method, query string, request JSON, response status, and response body.
3. Confirm protected requests contain `Authorization: Bearer <token>`.
4. Confirm `401` returns the user to login or shows an auth error.
5. Confirm `403` shows the permission message `لا تملك صلاحية لهذا الإجراء.`.
6. Confirm `422` shows `تحقق من البيانات المدخلة.`.
7. Inspect **Console** for uncaught exceptions and failed static resources.
8. Keep the backend terminal visible and correlate request lines with UI actions.
9. For scraper tests, inspect backend logs for source status transitions: `pending`, `active`, or `failed`.
10. Never paste JWTs or Apify tokens into screenshots or bug reports.

## 11. Completion Record

| Area | Result | Notes |
|---|---|---|
| Backend health/docs | [ ] | |
| Login/logout | [ ] | |
| Session refresh | [ ] | |
| Dashboard data | [ ] | |
| Topic switching | [ ] | |
| Source CRUD | [ ] | |
| Apify payload | [ ] | |
| Keyword CRUD | [ ] | |
| News filtering | [ ] | |
| RBAC denial checks | [ ] | |
| Invalid URL `422` | [ ] | |
| Scraper trigger | [ ] | API-only currently |
| Password reset | N/A | UI not implemented |
| User management UI | N/A | API/Swagger only |
| Audit logs UI | N/A | No log model/UI currently |
