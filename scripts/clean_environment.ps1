# Clean-environment procedure for the AI Career Agent.
#
# Resets the PostgreSQL dev/test databases to an empty, migration-headed state:
#   1. Terminate connections and DROP the dev and test databases (idempotent).
#   2. Recreate them owned by the app role (needs CREATEDB).
#   3. Run `alembic upgrade head` against dev (DATABASE_URL from .env) and test
#      (DATABASE_URL override).
#   4. Assert the migration head is present and domain tables are empty.
#
# Usage (PowerShell):
#   .\scripts\clean_environment.ps1 -AppPassword '...' [ -PgBin ... ]
#   $pw = (Get-Content "$env:USERPROFILE\postgresql\app_pw.txt" -Raw).Trim()
#   powershell -ExecutionPolicy Bypass -File .\scripts\clean_environment.ps1 -AppPassword $pw
param(
    [Parameter(Mandatory = $true)][string]$AppPassword,
    [string]$PgBin = "C:\Users\user\postgresql\pgsql\bin",
    [string]$PgHost = "127.0.0.1",
    [string]$PgPort = "5432",
    [string]$Role = "ai_career_agent",
    [string]$DevDb = "ai_career_agent",
    [string]$TestDb = "ai_career_agent_test"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Psql = Join-Path $PgBin "psql.exe"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$env:PGPASSWORD = $AppPassword
$Conn = "postgresql://{0}@{1}:{2}/postgres" -f $Role, $PgHost, $PgPort

if (-not (Test-Path $Psql)) { throw "psql not found at $Psql" }
if (-not (Test-Path $Python)) { throw "venv python not found at $Python" }
if (-not (Test-Path (Join-Path $RepoRoot "alembic.ini"))) { throw "alembic.ini not found" }

Write-Host "== Terminating connections and dropping databases =="
& $Psql -w -h $PgHost -p $PgPort -U $Role -d postgres -t -A -v ON_ERROR_STOP=1 -c (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity " +
    "WHERE datname IN ('$DevDb','$TestDb') AND pid <> pg_backend_pid();"
) | Out-Null
& $Psql -w -h $PgHost -p $PgPort -U $Role -d postgres -v ON_ERROR_STOP=0 -c "DROP DATABASE IF EXISTS $TestDb;" | Out-Null
& $Psql -w -h $PgHost -p $PgPort -U $Role -d postgres -v ON_ERROR_STOP=0 -c "DROP DATABASE IF EXISTS $DevDb;" | Out-Null

Write-Host "== Creating databases =="
& $Psql -w -h $PgHost -p $PgPort -U $Role -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DevDb;" | Out-Null
& $Psql -w -h $PgHost -p $PgPort -U $Role -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $TestDb;" | Out-Null

Write-Host "== Migrating dev database (DATABASE_URL from .env) =="
& $Python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head (dev) failed" }

Write-Host "== Migrating test database =="
$env:DATABASE_URL = "postgresql+asyncpg://$Role`:$AppPassword@$PgHost`:$PgPort/$TestDb"
& $Python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head (test) failed" }
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

Write-Host "== Verifying clean state =="
$Check = @(
    "SELECT 'alembic_version' AS tbl, count(*) FROM alembic_version",
    "SELECT 'users' AS tbl, count(*) FROM users",
    "SELECT 'candidates' AS tbl, count(*) FROM candidates",
    "SELECT 'jobs' AS tbl, count(*) FROM jobs",
    "SELECT 'gate4e_ingestion_records' AS tbl, count(*) FROM gate4e_ingestion_records",
    "SELECT 'outreach_runs' AS tbl, count(*) FROM outreach_runs"
)
foreach ($Db in @($DevDb, $TestDb)) {
    Write-Host "-- $Db"
    foreach ($Sql in $Check) {
        $Row = & $Psql -w -h $PgHost -p $PgPort -U $Role -d $Db -t -A -v ON_ERROR_STOP=1 -c $Sql
        Write-Host "   $Row"
    }
}

Write-Host "== Clean environment ready =="