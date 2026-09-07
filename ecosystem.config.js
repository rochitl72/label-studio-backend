/**
 * pm2 process definition for the RBG Annotation Studio backend.
 *
 * pm2 keeps uvicorn alive. PostgreSQL is installed and managed separately,
 * by whoever provisions the server. Nothing here needs a container.
 *
 * The database connection and other secrets are NOT configured here — they
 * live in db_config.py and config.py at this repo's root (see those files),
 * which the running app reads directly (see app/core/config.py). Every
 * deploy excludes both files from the sync (see
 * .github/workflows/deploy.yml), so real values entered on the server
 * persist across updates.
 *
 * One-time setup, before the first `pm2 start`:
 *
 *     python3 -m venv .venv
 *     .venv/bin/pip install -r requirements.txt
 *     $EDITOR db_config.py     # fill in the real database credentials
 *     $EDITOR config.py        # fill in SECRET_KEY, admin password, storage paths
 *     .venv/bin/alembic upgrade head
 *     mkdir -p logs
 *
 * Then:
 *
 *     pm2 start ecosystem.config.js && pm2 save
 *
 * A later deploy that changes requirements.txt or adds a migration needs the
 * matching command re-run by hand:
 *
 *     .venv/bin/pip install -r requirements.txt   # if dependencies changed
 *     .venv/bin/alembic upgrade head               # if the schema changed
 *
 * Neither is automatic — deploy.yml only copies files and reloads pm2, the
 * same as the org's other pm2-managed services.
 */
const path = require("path");

const ROOT = __dirname;
const VENV = process.env.RBG_VENV || path.join(ROOT, ".venv");

module.exports = {
  apps: [
    {
      name: "rbg-backend",
      // uvicorn is a real executable in the venv, so pm2 must not try to run
      // it through node. interpreter: "none" is what makes pm2 exec it
      // directly.
      script: path.join(VENV, "bin", "uvicorn"),
      interpreter: "none",
      args:
        "app.main:app" +
        ` --host ${process.env.BIND_HOST || "127.0.0.1"}` +
        ` --port ${process.env.BIND_PORT || "8000"}` +
        ` --workers ${process.env.UVICORN_WORKERS || "1"}`,
      // Single worker by default, matching the Docker deployment (the
      // connection pool and in-process assumptions were sized for that).
      // Raise UVICORN_WORKERS only after checking DB_POOL_SIZE/
      // DB_MAX_OVERFLOW in config.py can cover worker_count x pool_size
      // connections.
      cwd: ROOT,
      env: {
        PYTHONUNBUFFERED: "1",
      },
      autorestart: true,
      max_restarts: 10,
      max_memory_restart: "1G",
      out_file: path.join(ROOT, "logs", "backend-out.log"),
      error_file: path.join(ROOT, "logs", "backend-err.log"),
      merge_logs: true,
      time: true,
    },
  ],
};
