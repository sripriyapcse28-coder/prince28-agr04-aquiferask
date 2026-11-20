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


## D03 · PostgreSQL EXPLAIN and GIN index

### Query plan: normal execution

```text
Seq Scan on documents  (cost=0.00..1.04 rows=1 width=36) (actual time=0.016..0.017 rows=3.00 loops=1)
  Filter: (metadata @> '{"assessment_year": "2023"}'::jsonb)
  Buffers: shared hit=1
Planning:
  Buffers: shared hit=124 read=1
Planning Time: 1.463 ms
Execution Time: 0.042 ms
```

### Query plan: sequential scan disabled

```text
Bitmap Heap Scan on documents  (cost=8.52..12.54 rows=1 width=36) (actual time=0.048..0.049 rows=3.00 loops=1)
  Recheck Cond: (metadata @> '{"assessment_year": "2023"}'::jsonb)
  Heap Blocks: exact=1
  Buffers: shared hit=3
  -> Bitmap Index Scan on ix_documents_metadata_gin (cost=0.00..8.52 rows=1 width=0) (actual time=0.008..0.008 rows=3.00 loops=1)
       Index Cond: (metadata @> '{"assessment_year": "2023"}'::jsonb)
       Index Searches: 1
       Buffers: shared hit=2
Planning:
  Buffers: shared hit=1
Planning Time: 0.076 ms
Execution Time: 0.087 ms
```

### Why did PostgreSQL choose a Seq Scan?

The documents table is small, so scanning all its rows is cheaper than using the index. A sequential scan is efficient for small tables.

### When would PostgreSQL switch to the GIN index?

As the table grows and the query becomes more selective, PostgreSQL may choose the GIN index to locate matching JSONB records without scanning the entire table.

### Verification

- Database migration: `53027269c641 (head)`
- Index: `ix_documents_metadata_gin`
- Query: `metadata @> '{"assessment_year": "2023"}'::jsonb`
- Index usage confirmed by `Bitmap Index Scan`.
- Command: `uv run python scripts/explain.py assessment_year 2023`
