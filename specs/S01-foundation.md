# S01 — Repo foundation and CI

| | |
|---|---|
| Phase | 1 |
| Depends on | — |
| Branch | `feat/S01-foundation` |
| Design sections | الرؤية المعمارية › الطبقات؛ البيانات والتشغيل › الـ CI/CD؛ خارطة الطريق › المراحل (1) |
| ADRs | 0001 (layers) |

## Goal
The starter repo (this one) is committed, `make check` and CI are green, Postgres and MinIO start
locally, and Alembic has an empty baseline. Nothing product-specific yet.

## Scope
- In: tooling configs, package skeleton, docker compose, Alembic init + empty baseline, CI, pre-commit,
  commit-message check, Claude Code config, branch protection checklist.
- Out (→ S05): any table.

## Files
- Everything in the starter repo (already present).
- `alembic.ini`, `migrations/env.py` (async engine from `TE_DATABASE_URL`), `migrations/versions/0001_baseline.py` (no-op).
- `src/transcribe_engine/infrastructure/settings.py` — `Settings(BaseSettings)` with `env_prefix="TE_"`.
- `tests/integration/test_migrations.py` — upgrade/downgrade round trip.

## Rules
- Layers enforced by import-linter contracts in `pyproject.toml` `[D: الطبقات]`.
- CI order: lint + types + architecture → unit → integration `[D: الـ CI/CD]`.
- Python 3.12, `uv` `[D: المراحل 1]`.

## Acceptance criteria
- **AC-1** `[D: الطبقات]` — `make check` passes on a clean clone after `make setup`.
- **AC-2** `[D: الطبقات]` — adding `import fastapi` to any `domain` module makes `make check` fail
  (verified once manually, recorded in the PR; not committed).
- **AC-3** `[D: المراحل 1]` — `make up` brings Postgres and MinIO to healthy; `make migrate` succeeds.
- **AC-4** `[D: المراحل 1]` — `tests/integration/test_migrations.py::test_round_trip` (integration):
  upgrade head → downgrade base → upgrade head on a Testcontainers Postgres.
- **AC-5** `[D: الـ CI/CD]` — CI runs `check`, `integration`, `commits` jobs on a PR and all pass.
- **AC-6** — a commit message `fixed stuff` is rejected by the commit-msg hook and by CI.

## Manual setup (GitHub, once)
- Protect `main`: require PR, require `check` + `integration` + `commits`, require linear history,
  block force push, auto-delete head branches.
- Allowed merge method: **Rebase and merge** only (keeps step commits; see CONTRIBUTING.md).

## Commit plan
1. `chore(repo): add starter repo` (the files as delivered)
2. `docs(S01): add spec`
3. `build(S01): add settings and alembic baseline`
4. `test(S01): add migration round-trip test`
5. `ci(S01): verify pipeline on first PR` (only if CI needed fixes)

## Open questions
- [ ] Q1 — GitHub or another host? CI file assumes GitHub Actions.
