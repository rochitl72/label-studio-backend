# RBG Annotation Studio — Backend

FastAPI API for the RBG Annotation Studio image-annotation platform. This is
the **no-Docker, physical-server deployment** of this service — PM2 keeps it
running, PostgreSQL is installed natively, and the database connection and
secrets live in two plain config files at this repo's root rather than a
`.env` file. The user interface is a separate repository — see
**label-studio-frontend** — served by nginx, which also forwards `/api/` and
`/health` to this process.

---

## Requirements

- Python 3.11 or 3.12 (3.13 lacks prebuilt wheels for some dependencies)
- PostgreSQL 16.x — this is what the app has been built and tested against;
  request this specific major version if the server's Postgres isn't
  provisioned yet
- Two OS-level system libraries for image processing: `libglib2.0-0` and
  `libgl1` (Debian/Ubuntu package names — install with `apt-get install`
  before the first run, or the app will fail on import)
- `pm2` (`npm install -g pm2`)
- nginx (or equivalent) in front of this — see label-studio-frontend's
  `nginx/` folder for the reverse-proxy template

---

## What you should have received

Three things. Only the first is this repository.

| | What | How it arrives |
|---|---|---|
| 1 | This repository | git |
| 2 | A PostgreSQL dump (`db.dump`) — only if this is a migration of an existing install, not a fresh one | separately, over email |
| 3 | Real values for `db_config.py` and `config.py` below | filled in directly on the server, or sent separately for reference |

---

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configure the database connection

```bash
$EDITOR db_config.py   # fill in DB_CONFIG: dbname, user, password, host, port
```

`db_config.py` is the single place the running application's database
connection is configured. It ships in this repo with placeholder
(`CHANGE_ME`) values, and every future deploy excludes this exact file from
the sync (see `.github/workflows/deploy.yml`), so once you fill in the real
values here they persist across every subsequent `git push` to this repo.

### 3. Configure secrets and paths

```bash
$EDITOR config.py
```

Fill in at minimum:

- `SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `BOOTSTRAP_ADMIN_PASSWORD` — the first admin account's password (seeded only
  once, on an empty database)
- `STORAGE_DIR` / `EXPORT_DIR` — absolute paths on **this server** where
  uploaded images, overlays, exports and logs will live. Put these on a real
  data disk, not the system volume — budget roughly 3x your raw image set's
  size (see the on-disk layout note at the bottom of this file).

Like `db_config.py`, this file is excluded from every future deploy sync, so
it's a one-time edit.

### 4. Set up the database schema

```bash
.venv/bin/alembic upgrade head
```

This creates every table. It's idempotent — safe to re-run, and required
again after any future deploy that adds a migration (see "Updating" below).

If you received a `db.dump` (an existing install's data, not a fresh one),
restore it into the empty database *before* running the command above:

```bash
pg_restore --clean --if-exists -h <host> -U <user> -d <database> db.dump
alembic upgrade head   # applies any migrations newer than the dump
```

### 5. Start the process

```bash
mkdir -p logs
pm2 start ecosystem.config.js
pm2 save
```

`pm2 status` should show `rbg-backend` as `online`. Check it's actually
answering:

```bash
curl -i http://127.0.0.1:8000/health
```

Should return `{"status":"healthy"}` with a 200. If it doesn't come up, check
`logs/backend-err.log` first — a missing `SECRET_KEY` or a database it can't
reach are the two most common causes, and both fail loudly with a clear
message rather than starting in a broken state.

---

## Updating a deployed instance

Every `git push` to `main` triggers the deploy workflow, which copies the new
code and reloads the process — but it does **not** install new dependencies
or run new migrations automatically. After a push that changes either:

```bash
.venv/bin/pip install -r requirements.txt   # if requirements.txt changed
.venv/bin/alembic upgrade head               # if a new migration was added
pm2 reload rbg-backend                       # deploy.yml already does this, but
                                              # re-run manually if you skipped it
```

---

## Configuration reference

Every setting has a default and a description in `app/core/config.py`. The
two you actually edit — `db_config.py` and `config.py` — are documented
inline in those files. A short reference:

| Setting | Where | Meaning |
|---|---|---|
| `dbname` / `user` / `password` / `host` / `port` | `db_config.py` | PostgreSQL connection |
| `SECRET_KEY` | `config.py` | Signs login tokens. Changing it logs everyone out. |
| `BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | `config.py` | The first admin, seeded only when the database is empty |
| `STORAGE_DIR` / `EXPORT_DIR` | `config.py` | Where uploaded files and exports live on this server |
| `MAX_UPLOAD_MB` | `config.py` | Per-file upload cap (default 90) — must match nginx's `client_max_body_size` in the frontend repo's `nginx/` config, or whichever is smaller silently wins |
| `ENVIRONMENT` | `config.py` | Leave as `"production"` — enables fail-loud startup guards |
| `COOKIE_SECURE` | `config.py` | Set `true` once served over HTTPS |

**Passwords have no complexity rules** — any string is accepted, including an
empty one. Account security rests on choosing sensible values above.

---

## On-disk storage layout

Uploaded images are organised by role, then by user, under `STORAGE_DIR`:

```
<STORAGE_DIR>/
├── admin/{user_id}_{username}/project/{project_id}_{name}/images/{uuid}.jpg
├── admin/{user_id}_{username}/annotation/{project_id}_{name}/{json,overlays,coco,yolo,logs}/
└── users/{user_id}_{username}/...   (same structure)
```

Each annotated image is stored twice — the original, plus a rendered PNG
overlay — so budget roughly **3x** the size of the raw image set, plus room
for export bundles.

---

## Backups

```bash
pg_dump --format=custom -h <host> -U <user> <database> > db.dump
tar -czf storage.tar.gz -C "$(dirname <STORAGE_DIR>)" "$(basename <STORAGE_DIR>)"
```

Both halves are required — the database only stores file *paths*, not the
files themselves. Schedule this nightly with cron.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Backend won't start, complains about `SECRET_KEY` | Not set in `config.py` |
| Backend won't start, complains about the default admin password | `BOOTSTRAP_ADMIN_PASSWORD` in `config.py` is still the built-in default |
| `ModuleNotFoundError` on startup | The system packages `libglib2.0-0`/`libgl1` aren't installed, or the venv's `pip install` didn't complete |
| Images do not load | Check `STORAGE_DIR` in `config.py` matches where files actually are |
| Uploads rejected above a certain size | Check `MAX_UPLOAD_MB` here and `client_max_body_size` in the frontend repo's nginx config — both must allow the size you need |
| A deploy landed but nothing changed | New dependencies/migrations aren't applied automatically — see "Updating" above |

```bash
pm2 logs rbg-backend       # follow the live log
pm2 status                 # process health
tail -f logs/backend-err.log
```
