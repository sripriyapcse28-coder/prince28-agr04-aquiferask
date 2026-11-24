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
- Smoke test
