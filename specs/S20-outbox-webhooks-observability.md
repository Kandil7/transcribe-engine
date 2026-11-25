# S20 — Outbox, webhooks, observability

| | |
|---|---|
| Phase | 5 |
| Depends on | S08 |
| Branch | `feat/S20-outbox-webhooks-observability` |
| Design sections | تدفق البيانات › دورة الطلب (8)، نقاط النهاية (Webhooks)؛ نواتج النظام › التخزين والـ API (الأحداث)؛ البيانات والتشغيل › المراقبة |
| ADRs | — |

## Goal
Clients get signed, retried webhooks for each lifecycle event, and operators see every job through
structured logs, metrics, traces and alerts, without any transcript content leaking.

## Interfaces
```python
class OutboxEvent(StrEnum):
    TRANSCRIPT_COMPLETED = "transcript.completed"; TRANSCRIPT_FAILED = "transcript.failed"
    INDEX_COMPLETED = "index.completed"; ENRICHMENT_COMPLETED = "enrichment.completed"
class OutboxPublisher:   # use case loop
    async def run_once(self) -> int: ...
class WebhookSender(Protocol):
    async def send(self, url: str, body: bytes, headers: Mapping[str, str]) -> int: ...
def sign(body: bytes, secret: bytes, ts: int) -> str   # HMAC-SHA256 over f"{ts}.{body}"
def is_public_destination(url: str, resolve: Callable[[str], Sequence[IPAddress]]) -> bool
```

## Files
- `src/transcribe_engine/domain/{events,webhooks}.py`
- `src/transcribe_engine/application/use_cases/publish_outbox.py`
- `src/transcribe_engine/infrastructure/{http/webhook_sender,observability/{logging,metrics,tracing}}.py`
- `deploy/observability/alerts.yml`

## Rules
- Outbox rows written in the same transaction as the state change; publisher delivers at-least-once
  `[D: دورة الطلب 8]`.
- Events independent: transcript → index → enrichment `[D: التخزين والـ API]`.
- HMAC-SHA256 with timestamp header; retries with backoff up to 24 h `[D: نقاط النهاية]`.
- Destination resolved and rejected if private, loopback or link-local, at send time (SSRF).
- Logs: JSON, `job_id`, `tenant_id`, `stage`, `attempt` on every line, no content `[D: المراقبة]`.
- Metrics: queue depth (jobs and audio seconds), wait time, RTF per stage, failures by `error_code`,
  cache-hit ratio, suspect-segment ratio, lease expiries `[D: المراقبة]`. GPU via DCGM exporter (deploy).
- Traces: one span per stage linked by `job_id` `[D: المراقبة]`.
- Alerts: job in `QUEUED` > 30 min, failure rate > 5 % per hour, any `POISON_JOB` `[D: المراقبة]`.

## Acceptance criteria
- **AC-1** — `test_publish_outbox.py::test_event_written_with_state_change` (integration): rollback → no event.
- **AC-2** — `test_webhooks.py::test_signature_known_vector` (unit).
- **AC-3** — `test_webhooks.py::test_private_destinations_rejected` (unit): 127.0.0.1, 10/8, 169.254/16, ::1, DNS rebinding case.
- **AC-4** — `test_publish_outbox.py::test_retry_schedule_until_24h` (unit, fake clock).
- **AC-5** — `test_logging.py::test_no_transcript_text_in_logs` (unit): process a fake job with a marker
  word; captured logs never contain it.
- **AC-6** — `test_metrics.py::test_required_metrics_registered` (unit).
- **AC-7** — `promtool test rules` on `alerts.yml` (CI step).

## Commit plan
1. `docs(S20): add spec`
2. `test(S20): add outbox, webhook and observability tests (xfail)`
3. `feat(S20): write outbox events in state-change transactions`
4. `feat(S20): add signed webhook sender with SSRF guard`
5. `feat(S20): add outbox publisher with retries`
6. `feat(S20): add structured logging and metrics`
7. `feat(S20): add tracing spans per stage`
8. `build(S20): add alert rules`

## Open questions
- [ ] Q1 — Per-tenant webhook secret rotation: not in the design. Proposed: two active secrets per tenant.
