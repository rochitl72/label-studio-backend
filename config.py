# Deployment configuration — everything except the database connection
# (that lives in db_config.py, next to this file).
#
# Filled in by the deployment team, then left alone. Every deploy excludes
# this file from the sync (see .github/workflows/deploy.yml), so real values
# entered here persist across updates. Only fill in the CHANGE_ME
# placeholders — every other key already has a sane production default.
APP_CONFIG = {
    # Signs login tokens. REQUIRED — generate with:
    #   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    "SECRET_KEY": "CHANGE_ME",

    # First admin account, seeded only when the database is empty. REQUIRED —
    # must not be left at the built-in default (admin/123) on a real server.
    "BOOTSTRAP_ADMIN_USERNAME": "admin",
    "BOOTSTRAP_ADMIN_PASSWORD": "CHANGE_ME",
    "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",

    # Where uploaded images, overlays, exports and logs live on THIS server.
    # Use absolute paths — see README.md's storage section before deciding.
    "STORAGE_DIR": "CHANGE_ME",   # e.g. /var/lib/rbg-studio/storage
    "EXPORT_DIR": "CHANGE_ME",    # e.g. /var/lib/rbg-studio/exports

    # Per-file upload cap, in MB.
    "MAX_UPLOAD_MB": 90,

    # Enables the fail-loud guards (refuses to boot with a missing
    # SECRET_KEY or the default admin password). Always "production" here.
    "ENVIRONMENT": "production",

    # true once this is served over HTTPS (see nginx/ in the frontend repo),
    # so the auth cookie is only ever sent over TLS.
    "COOKIE_SECURE": True,
}
