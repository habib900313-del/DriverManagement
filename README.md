# Driver Management System

A fully offline, single-administrator driver management application for one
local Mac. Records live in a local **PostgreSQL** server; photos and documents
live on the local disk.
No cloud services, no external hosting, and no internet connection is needed
during normal operation.

> **Status: environment ready.** The toolchain is upgraded to Python 3.14.10 /
> Django 5.2.19 / DRF 3.18.3. The `Driver`, `Payment` and `Document` models and
> the business logic have **not** been implemented yet.

---

## 1. Environment (verified on this machine)

| Component | Version |
| --- | --- |
| macOS | 26.7.2 (Intel, x86_64) |
| Python | 3.14.10 (python.org universal2 framework build) |
| pip | 26.2.2 (inside `backend/.venv314`) |
| Django | 5.2.19 (LTS) |
| Django REST Framework | 3.18.3 |
| Node.js | 24.22.2 |
| npm | 11.19.1 |
| Vite | 8.3.6 |
| React | 19.3.1 |
| TypeScript | 7.0.2 |
| Tailwind CSS | 4.3.5 |
| SQLite | 3.50.4 (Python) / 3.51.0 (CLI) |
| OpenSSL | 3.5.9 |
| Git | 2.50.1 |

**Runtime:** the active backend environment is `backend/.venv314` (Python
3.14.10). Official Python 3.14 support starts with Django 5.2.8; the project is
pinned to the latest 5.2 LTS patch, **5.2.19**. DRF 3.18.3 officially supports
Python 3.14 and Django 5.2. The legacy `backend/.venv` (Python 3.9.6 / Django
4.2.30) is retained for rollback only and must not be used for development.

SSL certificates for the Python 3.14 interpreter were installed with the
official `/Applications/Python 3.14/Install Certificates.command` (certifi
2026.10.23); HTTPS verification works normally.

---

## 2. Directory structure

```
DriverManagement/
├── backend/        Django project + DRF API
├── frontend/       React + TypeScript + Tailwind (Vite)
├── storage/        Runtime files: uploaded photos and documents
├── backups/        Timestamped SQLite backups
├── scripts/        Start, admin creation and backup helpers
└── README.md       This file
```

### `backend/`

- `manage.py` — Django entry point.
- `config/` — project settings (`settings.py`, `urls.py`, WSGI/ASGI).
  - `config/local_settings.py` — machine-local secret key; **git-ignored**.
- `apps/core/` — system endpoints (`/api/health/`), no models.
- `apps/drivers/` — reserved for the `Driver` model and API (empty for now).
- `apps/payments/` — reserved for the `Payment` model and API (empty for now).
- `apps/documents/` — reserved for the `Document` model and API (empty for now).
- `db.sqlite3` — legacy SQLite database, no longer the primary store
  (git-ignored).
- `.env.postgres` — machine-local PostgreSQL connection settings, loaded
  automatically by `backend/config/settings.py` (git-ignored).
- `.venv314/` — **active** Python 3.14 virtual environment (git-ignored).
- `.venv/` — legacy Python 3.9 environment, kept for rollback (git-ignored).
- `requirements.txt` — pinned backend dependencies.

The app packages are separated by domain so each concern can grow without a
monolithic module. Only the three approved custom models will be added to them.

### `frontend/`

- `src/lib/api.ts` — typed fetch wrapper; all calls use relative `/api` paths.
- `src/App.tsx` — initial dashboard shell and backend status card.
- `src/index.css` — Tailwind import and base styles.
- `vite.config.ts` — Vite plugins and local API/media proxy.
- `dist/` — production build output (generated, git-ignored).

### `storage/`

Holds runtime files outside the code tree:

```
storage/
└── media/
    └── drivers/<driver-code>/
        ├── photos/
        └── documents/
```

Nothing is stored here yet; the per-driver folders will be created
automatically during uploads in a later phase. Only paths and metadata are
saved in the database.

### `backups/`

Timestamped backups produced by `scripts/backup-db.sh` (SQLite) and by
`pg_dump` for PostgreSQL, e.g. `db-20261107-144500.sqlite3`. Media should be
backed up alongside the database (e.g. with Time Machine or a copied folder).

### `scripts/`

- `start-backend.sh` — Django on `127.0.0.1:8000`.
- `start-frontend.sh` — Vite on `127.0.0.1:5173`.
- `start-all.sh` — both servers; Ctrl+C stops both.
- `create-admin.sh` — create the single administrator (Django auth).
- `backup-db.sh` — consistent SQLite backup of the legacy store.
- `backup-postgres.sh` — consistent PostgreSQL backup of the primary database
  (`pg_dump`, online, no downtime); prints the restore command.

---

## 3. Running the application

From the project root:

```bash
# Terminal 1 — backend
./scripts/start-backend.sh

# Terminal 2 — frontend
./scripts/start-frontend.sh
```

Or start both in one terminal:

```bash
./scripts/start-all.sh
```

Open: <http://127.0.0.1:5173>

The scripts use the active environment `backend/.venv314` automatically. Set
`DM_VENV=/path/to/venv` to override it temporarily.

The first-run dashboard calls `GET /api/health/`. A green **Connected** badge
confirms Django, PostgreSQL and the Vite proxy are all working.

### Create the administrator (one-time)

```bash
./scripts/create-admin.sh
```

This uses Django's built-in `User` model — no custom users table exists. The
Django admin is available at <http://127.0.0.1:8000/admin/>.

### Back up the database

```bash
./scripts/backup-db.sh
```

---

## 4. Setup history

1. Created the project directory skeleton.
2. Created `backend/.venv` with Python 3.9.6.
3. Installed Django 4.2.30 and DRF 3.16.1, pinned in `requirements.txt`.
4. Scaffolded Django project `config` and domain app packages.
5. Configured SQLite at `backend/db.sqlite3` with a 20-second busy timeout.
   (Later replaced by PostgreSQL as the primary database.)
6. Configured local media at `storage/media` (served only in DEBUG).
7. Generated `config/local_settings.py` with a random secret key.
8. Ran Django system checks and built-in migrations (admin/auth/sessions only).
9. Scaffolded React + TypeScript with Vite and installed Tailwind CSS v4.
10. Added a Vite proxy for `/api` and `/media` (no CORS package needed).
11. Added start, admin-creation and backup scripts plus `.gitignore`.
12. Verified `GET /api/health/` through the frontend proxy (HTTP 200).
13. Installed Python 3.14.10 (python.org), configured SSL certificates, and
    created `backend/.venv314`.
14. Installed Django 5.2.19 + DRF 3.18.3 and updated `requirements.txt`.
15. Verified Django/DRF on an independent copy of the backend and database:
    `check`, `showmigrations`, `migrate --plan`, auth, health API, media,
    timezone, Vite proxy, lint and production build. No migration was required,
    and the main database was left unchanged.
16. Retained `backend/.venv` (Python 3.9) for rollback; scripts now target
    `.venv314`.

No custom database models were created, as instructed.

---

## 5. Key configuration decisions

- **Offline by design.** Django and Vite bind to `127.0.0.1` only. No external
  services, CDNs, cloud storage or telemetry are used.
- **No custom User model.** Django's built-in authentication is used; the
  default `AUTH_USER_MODEL` is untouched.
- **API authenticated by default.** DRF's default permission is
  `IsAuthenticated`; only the health endpoint is public. Session authentication
  will pair with Django's login view in the next phase.
- **Single origin in development.** The browser talks only to
  `127.0.0.1:5173`; Vite proxies `/api` and `/media` to Django. This avoids
  adding `django-cors-headers`.
- **Media outside the source tree.** `MEDIA_ROOT` is `storage/media`, so the
  database stores relative paths and the files remain easy to back up.
- **Timezone `Asia/Kabul`.** Fee periods and due dates are evaluated as local
  calendar dates. Currency will be AFN (600 AFN quarterly fee) in the next phase.
- **Upload limits.** Requests up to 50 MB; files over 5 MB stream to disk.
- **Secret key.** Generated locally, stored in `config/local_settings.py`, and
  excluded from version control.

---

## 6. Business rules reserved for the next phase

Not implemented yet, recorded here so the data model stays aligned:

- Standard quarterly fee: **600 AFN**, with partial payments allowed.
- Outstanding debt is computed automatically, counting **only periods whose due
  dates have passed**.
- Unique driver code and unique driver identifier.
- Plate-number validation against accidental duplicates.
- Per-driver folders with collision-safe file names (never overwrite uploads).

---

## 7. Troubleshooting

**`Failed to fetch` / red "Offline" badge**
Start the backend (`./scripts/start-backend.sh`). The frontend proxy needs
Django on port 8000.

**Port already in use**
```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

**Back up PostgreSQL**
```bash
./scripts/backup-postgres.sh      # -> backups/drivermanagement-pg-<stamp>.sql
```
The script prints the exact `createdb` + `psql -f` commands to restore the
dump into a scratch database.

**Reset the local database (development only)**
Stop the servers, then drop and recreate the PostgreSQL database and run
`backend/.venv314/bin/python backend/manage.py migrate`. This destroys all data.

```bash
cd backend
dropdb -h 127.0.0.1 -U driverapp drivermanagement
createdb -h 127.0.0.1 -U driverapp -O driverapp drivermanagement
.venv314/bin/python manage.py migrate
```

**Regenerate the secret key**
Delete `backend/config/local_settings.py` and re-run the setup step described
in section 4; all sessions will be invalidated.

---

## 8. Next step

Awaiting approval to implement the three models (`Driver`, `Payment`,
`Document`), their validators, file-path helpers and REST endpoints.
