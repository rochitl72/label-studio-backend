# Database configuration — filled in by the deployment team, then left alone.
#
# Every deploy excludes this file from the sync (see
# .github/workflows/deploy.yml), so real values entered here persist across
# updates. Only the placeholder values need to change — the keys/shape below
# are exactly what's expected.
DB_CONFIG = {
    "dbname": "CHANGE_ME",
    "user": "CHANGE_ME",
    "password": "CHANGE_ME",
    "host": "CHANGE_ME",
    "port": "5432",
}
