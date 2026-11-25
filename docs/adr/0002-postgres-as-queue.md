# 0002. Postgres is both source of truth and job queue
Status: Accepted
Date: 2026-11-24   Slice: S06

## Context
Load is tens to hundreds of jobs per hour, each minutes long. With Redis + Celery the job row and the
queue message are two writes in two systems (lost or stuck jobs), Redis `visibility_timeout` redelivers
jobs longer than one hour, and Celery + Redis has no built-in dead-letter queue.

## Decision
The job row is the queue message. Workers claim with `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED
LIMIT 1)`, hold a lease extended by heartbeats, and write results with fencing on
`(lease_owner, attempt_count)`. A reconciler handles expired leases and due retries; `attempt_count` in
the DB replaces a dead-letter queue (`FAILED(POISON_JOB)`).

## Alternatives considered
- Redis + Celery: rejected for the reasons above.
- RabbitMQ: real DLQ and acks, but still a second system to keep consistent; revisit only if
  Postgres claim latency or lock contention shows up in metrics.

## Consequences
- One transaction covers state change, outbox event and enqueue.
- We own lease/heartbeat/fencing code (S06) and its chaos tests.
