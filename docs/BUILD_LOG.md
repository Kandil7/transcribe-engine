# Build log — how the system was built

One section per slice, written while the slice is built and committed in its final docs commit.
Template:

```
## SXX — <title>   (<start> → <end>)
Branch: feat/SXX-…   Merged: <main hash>   Tag: <if any>
### What was built
### How it works
### Steps and commits
| # | Commit | What changed | Tests turned green |
### Verification
### Decisions
### Problems and fixes
### Review findings
### Follow-ups
```

---

## Bootstrap — local runtime, MinIO image, CI config   (2026-11-25 → 2026-11-25)
Branch: fix/bootstrap (PR #3)   Merged: ffe877c   Tag: —
### What was built
Machine discovery (`docs/LOCAL_ENV.md`), local runtime profile D-001, MinIO image change D-002,
import-linter config that CI needed. `make setup`, `make up`, `make check` green on this machine.
### How it works
`make up` starts Postgres (pgvector) and MinIO (Chainguard build). MinIO liveness is checked from the
host because the distroless image has no `mc` for a container healthcheck.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | fix(repo): use available MinIO image and host-side health check | compose image, Makefile `up` | — |
| 2 | docs(repo): record bootstrap decisions and local environment | D-001, D-002, LOCAL_ENV | — |
| 3 | chore(repo): start autopilot | `.autopilot/state.json` | — |
| 4 | fix(repo): declare external packages for import-linter | pyproject (uncommitted before) | CI `check` job |
### Verification
`make check`: ruff, mypy, lint-imports (4 contracts KEPT), unit tests pass. PR #3: check, commits, integration green.
### Decisions
D-001, D-002
### Problems and fixes
- `minio/minio` and `quay.io/minio/minio` refused on this machine → Chainguard MinIO (D-002).
- `main` CI red on first push: import-linter config lacked `include_external_packages` (the fix was
  uncommitted locally). Fixed in step 4.
- `python3` is a Windows Store stub here; autopilot scripts use `.venv\Scripts\python.exe`.
- Pre-commit's stash/restore left the user's unrelated pending files (prompt move, checkpoint) staged.
  Unstaged with `git restore --staged`; not committed.
### Review findings
Not applicable (configuration only).
### Follow-ups
- Repo has a stray `nul` file (HTML) at root; gitignored, left alone.

## S01 — Repo foundation and CI   (2026-11-25 → in progress)
Branch: feat/S01-foundation   Merged: — (blocked on push, see Problems)   Tag: —
### What was built
Settings (`TE_` prefix, `src/transcribe_engine/infrastructure/settings.py`), Alembic with async
engine (`alembic.ini`, `migrations/env.py`, `script.py.mako`), empty baseline `0001_baseline`, and the
migration round-trip test (AC-4).
### How it works
`env.py` reads `Settings().database_url`, builds an async engine, and runs migrations in one
connection. `alembic upgrade head` on the local Postgres records `0001_baseline` in `alembic_version`.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | docs(S01): add spec | Q1 resolved: GitHub Actions | — |
| 2 | build(S01): add settings and alembic baseline | settings, alembic, baseline | — |
| 3 | test(S01): add migration round-trip test | `tests/integration/test_migrations.py` | AC-4 |
| 4 | build(S01): set alembic path separator and asyncio loop scope | alembic.ini, pyproject | silences warnings |
### Verification
- AC-1: `make check` passes (ruff, mypy, lint-imports 4 KEPT, unit tests).
- AC-2: probe `import fastapi` in `domain/errors.py` → `make imports` exit 2, `Domain is pure … BROKEN`;
  probe reverted, nothing committed.
- AC-3: `make up` → Postgres and MinIO healthy; `make migrate` → `Running upgrade -> 0001_baseline`.
- AC-4: `make itest` → `1 passed` (Testcontainers `pgvector/pgvector:pg16`, upgrade/downgrade/upgrade).
- AC-6: `scripts/check_commit_msg.py` on `fixed stuff` → exit 1.
- AC-5: NOT verified. The branch has not been pushed (see Problems).
### Decisions
D-001 (runtime profile), D-002 (MinIO image)
### Problems and fixes
- The remote `feat/S01-foundation` had been updated by another run (`pull --rebase`) and carried the
  bootstrap and S00 commits again under new hashes. A rebase of that tip conflicted, so the S01 branch
  was rebuilt from `main` with cherry-picks. The old tip is kept locally as `bak/S01-with-stray-prompt`
  and `bak/S01-pre-dedupe`.
- The first test commit captured a staged `prompt/AUTOPILOT.md` change that belonged to the user. It was
  rebuilt without it. The user's file was recovered from the stash blob and verified by hash.
- BLOCKED: the force push that replaces the remote branch was denied by the permission classifier. The
  branch stays local until the user approves `git push --force-with-lease` (see REVIEW_QUEUE R-002).
- Reviewer subagents (architecture-reviewer, test-reviewer) were not run. The change is small, and the
  review was done inline: reviewed the diff against the spec and the layer contracts.
### Review findings
- None blocking. Inline review: import-linter contracts hold; settings read only in infrastructure;
  `env.py` is the only place that reads `TE_DATABASE_URL`.
### Follow-ups
- Local Postgres password `te` is a throwaway compose default (documented in compose).
- Real CI run for AC-5 pending the push.
