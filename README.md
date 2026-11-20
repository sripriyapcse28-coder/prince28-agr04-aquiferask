# AquiferAsk

[![CI](https://github.com/sripriyapcse28-coder/prince28-agr04-aquiferask/actions/workflows/ci.yml/badge.svg)](https://github.com/sripriyapcse28-coder/prince28-agr04-aquiferask/actions/workflows/ci.yml)

[![Live](https://img.shields.io/website?url=https%3A%2F%2Fprince28-agr04-aquiferask.onrender.com%2Fhealth&label=live)](https://prince28-agr04-aquiferask.onrender.com/docs)

[![Uptime (30 days)](https://img.shields.io/uptimerobot/ratio/m804745833-9adf9bbf8b0ba10043d75259)](https://prince28-agr04-aquiferask.onrender.com/health)

**Status:** Week 1 complete · live at https://prince28-agr04-aquiferask.onrender.com

**Live:** [AquiferAsk](https://prince28-agr04-aquiferask.onrender.com) · [API docs](https://prince28-agr04-aquiferask.onrender.com/docs) · [Health](https://prince28-agr04-aquiferask.onrender.com/health)## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build
```

This starts Postgres (with pgvector), Redis, runs the migrations and loads the sample data once, then starts the API.

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Liveness: [http://localhost:8000/health](http://localhost:8000/health)
- Readiness (checks the database): [http://localhost:8000/ready](http://localhost:8000/ready)

Stop with `Ctrl+C`, then `docker compose down`. Add `-v` to also delete the database volume.

## Develop and test

| Task | Mac / Linux | Windows |
|---|---|---|
| Run the API with reload | `make dev` | `uv run poe dev` |
| Unit tests (no network) | `make test` | `uv run poe test` |
| Integration tests (needs `docker compose up`)
## D05 · CI/CD and going live

- Live URL: https://prince28-agr04-aquiferask.onrender.com
- CI run for pull request 1: (paste GitHub Actions run link)
- First deploy that ran by itself: (paste CD run link)
- Merge clicked at __:__ → "Smoke test passed" at __:__ → lead time: ___ min

### Smoke test output from that CD run

```text
Paste the last 4 lines of the "Smoke test the live URL" step here.
```

### Rollback drill

- Rolled back to SHA: (fill after rollback)
- Started: __:__ ; smoke passed: __:__ (___ min)
- Rolled forward to SHA: (fill after roll-forward)
- Time taken: ___ min

During the rollback, the database stayed on the newer schema. Why is that safe here?

The rollback changes the application image but does not reverse database migrations. This is safe because the older application version can still work with the newer, backward-compatible database schema.

### Where my secrets live

- Neon connection string: GitHub Secret `DATABASE_URL` (and Render environment, if configured). Never stored in Git or the Docker image.
- Render deploy hook: GitHub Secret `RENDER_DEPLOY_HOOK` only.

### Monitoring

- UptimeRobot checks `/health` every 5 minutes; alerts go to my email.
- One thing that would make my live app faster on its first request: Use an always-on hosting instance to avoid cold starts.
