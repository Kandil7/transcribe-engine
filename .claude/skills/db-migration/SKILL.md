---
name: db-migration
description: Create or change the database schema with Alembic safely.
---
1. Change SQLAlchemy models in `src/transcribe_engine/infrastructure/db/models.py`.
2. `uv run alembic revision --autogenerate -m "<what changed>"`; then read the generated file:
   autogenerate misses CHECK constraints, partial indexes, enum changes and extensions.
3. Never edit a migration that is already on `main`. Fix forward with a new revision.
4. Every migration has a working `downgrade()`, or raises with a clear message if irreversible.
5. Zero-downtime order for changes on live tables: add nullable column → backfill → add constraint
   → switch code → drop old column in a later slice.
6. Job states are enforced in the DB too: `CHECK (state IN (...))` must match `domain.jobs.JobState`.
   A test asserts the two lists are equal.
7. Test: `tests/integration/test_migrations.py` runs upgrade head → downgrade base → upgrade head
   on a Testcontainers Postgres.
