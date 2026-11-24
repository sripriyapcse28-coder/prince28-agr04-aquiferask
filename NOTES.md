
# AquiferAsk — Project Notes

## D05 · CI/CD, monitoring and rollback

### Live application

- Live URL: https://prince28-agr04-aquiferask.onrender.com
- API documentation: https://prince28-agr04-aquiferask.onrender.com/docs
- Health endpoint: https://prince28-agr04-aquiferask.onrender.com/health
- Readiness endpoint: https://prince28-agr04-aquiferask.onrender.com/ready

### GitHub Actions

- CI workflow: (paste the GitHub Actions CI run link)
- CD workflow: (paste the successful CD run link)
- Deployment was triggered automatically after CI completed successfully on `main`.
- The deployment used the exact Docker image associated with the commit SHA.
- Database migrations ran before the new application image was deployed.
- The live smoke test checked `/health`, `/ready`, and `/v1/documents?limit=1`.

### Smoke test verification

```text
ok   /health -> 200
ok   /ready -> 200, database: true
ok   /v1/documents?limit=1 -> 200
Smoke test passed
```

### Rollback drill

- Rolled back to SHA: `7bbce1b73bf4e5706caf413b4f9232e5654be2b5`
- Rollback workflow: Success
- Rollback smoke test: Passed
- Rolled forward to SHA: `a07d75ab862cb52949813c81a2fba2c850a51ff9`
- Roll-forward workflow: Success
- Roll-forward smoke test: Passed

During the rollback, the database stayed on the newer schema. Why is that safe here?

The rollback changes the application image but does not reverse database migrations. This is safe when the older application version remains compatible with the newer database schema. The rollback smoke test confirmed that the health, readiness, and documents endpoints worked with the older application version.

### Monitoring

- Monitoring service: UptimeRobot
- Monitor type: HTTP(s)
- Monitored endpoint: `/health`
- Monitoring interval: Every 5 minutes
- Email alerts: Enabled
- Monitor status: UP
- README includes CI, Live, and UptimeRobot 30-day uptime badges.

### Secrets

- Neon database connection string: GitHub Actions secret `DATABASE_URL`.
- Render deploy hook: GitHub Actions secret `RENDER_DEPLOY_HOOK`.
- Secrets are stored in the appropriate environment settings and are not committed to Git or included in the Docker image.

### Deployment timings

- Pull request merge time: (fill in)
- Smoke test passed time: (fill in)
- Deployment lead time: (fill in)
- Rollback duration: (fill in)
- Roll-forward duration: (fill in)

---

# Migration notes

## Escape-route test (downgrade one step, check, come forward)

Running downgrade 53027269c641 -> 2c25fac5af3e, add gin index on metadata

current: 2c25fac5af3e

Running upgrade 2c25fac5af3e -> 53027269c641, add gin index on metadata

## History

2c25fac5af3e -> 53027269c641 (head), add gin index on metadata

&lt;base&gt; -> 2c25fac5af3e, create documents and pages

## D04 · Docker, Compose and tests

### The image

Actual Compose image name: `aquiferask-api:latest` (the task's example tag `aquiferask:dev` is not used in this project).

```text
docker images aquiferask-api

IMAGE                   DISK USAGE   CONTENT SIZE
aquiferask-api:latest   300MB        70MB

docker images aquiferask-migrate

IMAGE                      DISK USAGE   CONTENT SIZE
aquiferask-migrate:latest  300MB        70MB

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
aquiferask-api-1        aquiferask-api           api       Up (healthy)
aquiferask-db-1         pgvector/pgvector:pg17   db        Up (healthy)
aquiferask-migrate-1    aquiferask-migrate       migrate   Exited (0)
aquiferask-redis-1      redis:7-alpine           redis     Up (healthy)
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



### Test results

| Run | Downloaded | Skipped | Blocked | Failed |
|---|---:|---:|---:|---:|
| First interrupted run | 8 | 0 | 1 | 0 |
| Second resumed run | 1 | 8 | 1 | 0 |
| Third run | 0 | 9 | 1 | 0 |
| Deleted-file recovery | 1 | 8 | 1 | 0 |

### Verification
- Completed downloads were preserved after interruption.
- Existing files were skipped during resume.
- Third run downloaded no new files.
- No incomplete `.part` files were found.
- Deleted PDF was successfully downloaded again.
- Robots.txt restrictions were respected.

**Result:** Downloader resume and recovery tests passed.


---

# D06 · Collecting the groundwater corpus
## Corpus collection

- Source: Central Ground Water Board (CGWB).
- Sources registered: 11.
- District brochures downloaded: 10.
- Existing Tamil Nadu Groundwater Assessment 2025 PDF: 1.
- Total documents: 11.
- Total pages: 355.
- Total storage: 49.82 MB.
- Target: 6,000 pages.
- Progress: 5.92%.

## Licence and robots.txt

- CGWB copyright policy permits free reproduction of its own materials when accurately presented with prominent source acknowledgement.
- Third-party copyrighted materials are excluded.
- Source: https://cgwb.gov.in/en/website-policies
- Robots file: https://cgwb.gov.in/robots.txt
- Robots.txt returned HTTP 200.
- All 11 source URLs were allowed.
- No robots restrictions were bypassed.

## Downloader results

Command: `uv run python scripts/fetch.py urls --delay 3`

- Downloaded: 10
- Skipped: 1
- Blocked: 0
- Failed: 0
- Time: 28.6 seconds.

## TLS issue

The initial downloader could not verify the CGWB SSL certificate. Installed `truststore` and configured the HTTP client to use the Windows trusted certificate store. Certificate verification remained enabled.

## Dataset and capacity

- `DATASET.md` generated successfully.
- `docs/CAPACITY.md` generated successfully.
- Current corpus: 355 pages and 49.82 MB.
- Remaining target: 5,645 pages.
- Estimated storage for 6,000 pages: 842.11 MB.

## Known gaps

- Only one assessment-year PDF is currently registered.
- More assessment years and district groundwater reports are needed.
- PDF text extraction, OCR validation and indexing remain future work.
- The assessment PDF shows a header warning, although its 130 pages were counted successfully.

## Validation

- Ruff check: passed.
- Unit tests: 38 passed.
- Downloader: 10 downloaded, 1 skipped, 0 blocked, 0 failed.

## What went wrong

The first downloader run failed because of a TLS certificate verification issue. Adding `truststore` resolved it without disabling certificate verification or bypassing robots.txt.
