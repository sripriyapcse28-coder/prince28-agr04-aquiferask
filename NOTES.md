# Migration notes

## Escape-route test (downgrade one step, check, come forward)

Running downgrade 53027269c641 -> 2c25fac5af3e, add gin index on metadata
current: 2c25fac5af3e
Running upgrade 2c25fac5af3e -> 53027269c641, add gin index on metadata

## History

2c25fac5af3e -> 53027269c641 (head), add gin index on metadata
<base> -> 2c25fac5af3e, create documents and pages

## D04 · Docker, Compose and tests

### The image

Actual Compose image name: `aquiferask-api:latest` (the task's example tag `aquiferask:dev` is not used in this project).

```text
docker images aquiferask-api

IMAGE                   DISK USAGE   CONTENT SIZE
aquiferask-api:latest   300MB        70MB

docker images aquiferask-migrate

IMAGE                       DISK USAGE   CONTENT SIZE
aquiferask-migrate:latest   300MB        70MB

docker run --rm aquiferask-api id

uid=999(app) gid=999(app) groups=999(app)
```

- Image size: 300 MB disk usage; 70 MB content size.
- First clean-clone build: approximately 26.7 seconds.
- Build after changing one line of code: not measured.
- Cached steps included the UV binary copy and `WORKDIR /app`. Docker reused unchanged layers instead of rebuilding them.

### The stack

```text
docker compose ps -a

NAME                   IMAGE                    SERVICE   STATUS
aquiferask-api-1       aquiferask-api           api       Up (healthy)
aquiferask-db-1        pgvector/pgvector:pg17   db        Up (healthy)
aquiferask-migrate-1   aquiferask-migrate       migrate   Exited (0)
aquiferask-redis-1     redis:7-alpine           redis     Up (healthy)
```

Fresh database migration:

```text
Running upgrade  -> 2c25fac5af3e, create documents and pages
Running upgrade 2c25fac5af3e -> 53027269c641, add gin index on metadata
records=3 inserted=3 updated=0 unchanged=0
```

After restarting with the existing database volume:

```text
records=3 inserted=0 updated=0 unchanged=3
```

The migration is idempotent: restarting the stack does not duplicate existing sample records.

### Breaking the database on purpose

Previously verified results:

```text
db stopped:
  /health -> {"status":"ok","app":"aquiferask","env":"local"}

  /ready -> {"status":"not_ready","checks":{"database":false}}

db started:
  /ready -> {"status":"ready","checks":{"database":true}}
```

The load balancer should stop sending traffic when readiness fails because the application cannot safely serve database-dependent requests. It should not restart the application because the process is still alive and restarting it will not fix an unavailable database.

### Tests and coverage

```text
uv run poe test              -> 16 passed
uv run poe test-integration  -> 7 passed

Coverage TOTAL, unit only: 83%
Coverage TOTAL, with integration tests: 92%
```

Areas with lower coverage from the previous report:
- `repository.py`: 27% coverage.
- `deps.py`: 64% coverage.

These are areas to investigate for uncovered lines; check the latest coverage report's `Missing` column before identifying exact lines that were never executed.
