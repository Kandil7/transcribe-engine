# Decision log

Every choice not fixed by a spec, ADR or earlier decision is recorded here, newest last. Big,
hard-to-reverse decisions also get an ADR in `docs/adr/`. A changed decision is never edited away:
add a new entry and mark the old one `superseded by D-NNN`.

Entry format:
```
## D-NNN — <title>
Date: YYYY-MM-DD · Slice: SXX · Status: decided | superseded by D-MMM · Review: none | requested
Context: <the question and why it came up>
Options: A) … B) … C) …
Decision: <choice>
Rationale: <why; cite [D: section], ADR, benchmark or test evidence>
Reversibility: easy | moderate | hard — <cost of undoing>
Confidence: high | medium | low
Applied in: <commit hashes>
```

---

<!-- D-001 is written by the autopilot bootstrap: local runtime profile for this machine. -->

## D-001 — Local runtime profile for this machine
Date: 2026-11-25 · Slice: bootstrap · Status: decided · Review: none
Context: Choosing the ASR runtime for local runs (§6.1). Machine: Windows 11 host, Docker Desktop
(Linux containers, WSL2 backend), NVIDIA Quadro RTX 5000 16 GB (Turing, compute 7.5), 12 cores,
32 GB RAM, 115 GB free on D:, FFmpeg 9.0 installed, uv 0.12, Docker Compose v5.6.
Options: A) vLLM BF16 container (production path, row "NVIDIA ≥ 16 GB") B) vLLM with a smaller variant
or faster-whisper on GPU in FP16 (row "NVIDIA 8–16 GB") C) CPU-only faster-whisper int8.
Decision: B — faster-whisper (CTranslate2) on the GPU in FP16 for the local ASR engine, selected by
`TE_ASR_PROFILE=local-gpu`. CPU worker stays for ingest/FFmpeg/plumbing. The vLLM BF16 adapter is still
built (S12) and remains the production target (ADR-0005).
Rationale: [D: §6.1]. Turing has no BF16 tensor support, so the "BF16 on vLLM" row cannot run here
as specified. FP16 on Turing is supported by CTranslate2. GPU passthrough through Docker Desktop is an
extra failure point, so the local path avoids depending on vLLM for the first demo. Selection is
configuration only; the pipeline does not branch on the profile (§6 rule).
Reversibility: easy — the profile is a setting; the Port hides the engine.
Confidence: medium — the choice of faster-whisper over vLLM is an inference from GPU generation and
Docker Desktop, not a measured benchmark. S00 measures RTF and memory on this machine.
Applied in: (bootstrap commit, see BUILD_LOG)

## D-002 — Local object storage image: Chainguard build of MinIO
Date: 2026-11-25 · Slice: bootstrap · Status: decided · Review: none
Context: `make up` failed: `minio/minio` and `quay.io/minio/minio` are not pullable from this machine
(access denied / unauthorized). Compose needs an S3-compatible server for S07.
Options: A) `cgr.dev/chainguard/minio:latest` — MinIO server build, pulls anonymously B) SeaweedFS or
Adobe S3Mock (pull was too slow to finish) C) LocalStack (large image, broader scope than needed).
Decision: A. Compose uses `cgr.dev/chainguard/minio:latest`; the compose healthcheck is removed because
the distroless image has no `mc`; `make up` checks `/minio/health/live` from the host instead.
Rationale: same S3 API and binary (`minio version RELEASE.2026-11-23…`), no login, smallest change.
License: MinIO server is AGPLv3. It runs only as a local dev container and is not distributed or linked
into this code; production S3 is a separate concern (S21/cloud).
Reversibility: easy — image name and healthcheck are in `docker-compose.yml` and `Makefile`.
Confidence: high for local dev.
Applied in: (bootstrap commit, see BUILD_LOG)

## D-003 — Attempt exhaustion is decided at the error (no RETRY_SCHEDULED → FAILED edge)
Date: 2026-11-25 · Slice: S02 · Status: decided · Review: none
Context: The design diagram shows `RETRY_SCHEDULED → FAILED (attempts exhausted)`, the transition table does
not. S02 spec Q1.
Options: A) Decide exhaustion on the error event (`PROCESSING → FAILED`), drop the diagram edge.
B) Keep the diagram edge and let the retry timer check the attempt count.
Decision: A, as proposed in the spec.
Rationale: [D: آليات الاعتمادية] one decision point per error keeps `transition()` pure and needs no timer
logic in the domain. The diagram edge is removed in `docs/design.md` in the S02 branch.
Reversibility: easy — one table row.
Confidence: high.
Applied in: S02 spec commit

## D-004 — Backoff defaults and jitter source
Date: 2026-11-25 · Slice: S02 · Status: decided · Review: none
Context: The design gives no backoff numbers. S02 spec Q2. `backoff()` takes no RNG parameter.
Options: A) Config defaults base 30 s, cap 10 min, jitter 0.2, jitter drawn with stdlib `random`.
B) Deterministic jitter derived from attempt number (no randomness).
Decision: A. Delay = min(cap, base · 2^(attempt−1)) scaled by a uniform factor in [1−jitter, 1+jitter] and
clamped to [0, cap]. `jitter=0` gives an exact, deterministic result.
Rationale: stdlib `random` is allowed in `domain`. Random jitter is what spreads retries out; a fixed
function of the attempt number does not. Bounds are testable with Hypothesis (AC-5).
Reversibility: easy — defaults are config.
Confidence: medium — numbers are a proposal, not measured.
Applied in: S02 spec commit

## D-005 — PROFILING stage added; STAGE_HANDOFF accepted per ADR-0006
Date: 2026-11-25 · Slice: S02 · Status: decided · Review: none
Context: Section 1.5 adds a profiling step absent from the design's stage list (S02 Q3). The
`PROCESSING → QUEUED` hand-off is not in the design table (S02 Q4, ADR-0006 Proposed).
Options: A) Add `PROFILING` after `NORMALIZING` and the `STAGE_HANDOFF` row; B) omit both.
Decision: A. ADR-0006 is accepted with this slice.
Rationale: the stage and the hand-off are both needed by S13 and S10; leaving them out would force later
schema changes.
Reversibility: easy — enum members and one table row.
Confidence: high.
Applied in: S02 spec commit

## D-006 — `transition()` takes an optional error code for permanent and validation failures
Date: 2026-11-25 · Slice: S02 · Status: decided · Review: none
Context: The spec says `VALIDATION_FAILED` and `PERMANENT_ERROR` go to `FAILED` with the code "from caller",
but the signature has no code parameter.
Options: A) Add keyword `error_code: ErrorCode | None = None`, required for those two events; B) a separate
function per event.
Decision: A. Missing code for those events raises `ValueError`.
Rationale: keeps the single `transition()` entry point from the spec; the keyword does not change any other
call.
Reversibility: easy.
Confidence: high.
Applied in: S02 spec commit

## D-007 — Key and ID encodings for S03
Date: 2026-11-25 · Slice: S03 · Status: decided · Review: none
Context: The design gives the key and ID formulas (`[D: مفتاح الـ Idempotency]`, `[D: التقسيم]`, `[D: الـ RAG]`)
but not how to encode the isolation scope or how to avoid separator collisions in `embedding_id`. S03 Q1 is
also answered here: routing policy changes bump `pipeline_version`, not a new key field.
Options: A) Raw `|`-joined strings everywhere. B) Canonical JSON arrays for every hashed tuple.
C) `|`-joined for ids whose parts cannot contain `|` (hex hashes, integers, transcript ids), canonical JSON
for `embedding_id`, whose text can contain any character.
Decision: C.
- `result_key = "res_" + sha256(file_sha256 + "‖" + canonical_json(config))`. When `isolation_scope` is
  given, `"‖" + isolation_scope` is appended to the hashed bytes. Without a scope, the bytes are unchanged, so
  shared-result keys are stable.
- `chunk_id = "chk_" + sha256("|".join(media_sha256, config_hash, idx, start, end))`.
- `rag_chunk_id = "rag_" + sha256("|".join(transcript_id, version, start_ms, end_ms))`; `transcript_id`
  containing `|` is rejected with `ValueError`.
- `embedding_id = "emb_" + sha256(canonical_json([text_with_header, embedding_model]))`.
- `language` must be non-empty and may not be `"auto"` (explicit language only, per the spec).
Rationale: the design formulas are followed literally where their parts are safe to join. The embedding text
is free text, so a JSON array removes any ambiguity between text and model name.
Reversibility: moderate — every stored key depends on these bytes; changing them later invalidates caches.
Confidence: high for the encodings; the choice is pinned by golden values in tests (AC-4).
Applied in: S03 spec commit

## D-008 — Normalizer lives in the domain as pure character rules (not CAMeL)
Date: 2026-11-26 · Slice: S04 · Status: decided · Review: none
Context: The design says "التنفيذ عبر CAMeL Tools بدل Regex يدوي". CLAUDE.md keeps `domain` on the standard
library, and S04 needs an exact offset map. S04 Q1.
Options: A) `TextNormalizer` Port with a CAMeL adapter in infrastructure. B) Character rules in
`domain/text.py` using `str.translate` and single-pass code; CAMeL reserved for morphology later.
Decision: B. ADR-0008 records it; the design sentence is updated.
Rationale: the rules are a fixed character table, so they are exact and testable without a dependency. A
Port with one implementation breaks the "no abstraction without a second implementation" rule. The
offset map is exact only when each rule is 1:1 or a deletion, which CAMeL's output does not guarantee.
Reversibility: easy — a morphology adapter can be added later behind a Port without changing these rules.
Confidence: high.
Applied in: S04 spec commit

## D-009 — Persian yeh folds to Arabic yeh; Persian kaf does not
Date: 2026-11-26 · Slice: S04 · Status: decided · Review: none
Context: The design does not mention Persian/Urdu letters. S04 Q2.
Options: A) Fold ی and ک to ي and ك. B) Fold only ی. C) Fold nothing.
Decision: B. ی (U+06CC) → ي (U+064A).
Rationale: in Egyptian text, ی appears as a typing variant of ي; ک is not a common variant there, and folding
it would change words that are distinct in Arabic.
Reversibility: easy — one table row.
Confidence: medium — a judgement, to check against the case table.
Applied in: S04 spec commit

## D-010 — Exact definitions of the 1:1 rules for whitespace and case
Date: 2026-11-26 · Slice: S04 · Status: decided · Review: none
Context: Rule 6 (collapse whitespace) maps many characters to one, which the spec's "1:1 or deletion" rule does
not allow. Rule 7 (lowercase) can change length (for example U+0130 lowercases to two characters). AC-3 as
written would reject a tab that becomes a space.
Options: A) Keep the rules literal and drop the offset guarantee. B) Express collapse as "keep first,
delete the rest" and lowercase per character only when the result is one character. C) Lowercase ASCII only.
Decision: B. AC-3 accepts a whitespace raw char for a space in `search`.
Rationale: keeps the offset map exact, which search and RAG depend on. Option C would leave other Latin
letters unfolded, which is not what rule 7 says.
Reversibility: easy — internal to `text.py`.
Confidence: high.
Applied in: S04 spec commit

## D-011 — Correct the alef-variant case row (fixture expectation error)
Date: 2026-11-26 · Slice: S04 · Status: decided · Review: none
Context: The case row `أإآٱ` was written with expected `االا` (lam in it). Rule 1 maps all four characters to
alef, so the correct expectation is four alefs. The first run of `test_cases_table` failed on this row.
Options: A) Change the implementation to match the wrong row. B) Correct the row. C) Delete the row.
Decision: B. The fixture row is corrected in its own commit; the rule itself is unchanged.
Rationale: the rule (1) and its design source are clear; only the expectation was mistyped.
Reversibility: easy.
Confidence: high.
Applied in: fix(S04) commit for the fixture row

## D-012 — map_span includes deleted marks that sit inside a word
Date: 2026-11-26 · Slice: S04 · Status: decided · Review: none
Context: The spec's edge case says a span that starts or ends on a deleted character maps to the nearest kept
neighbour. But AC-4 requires the full raw word with its diacritics, and the architecture review found that
a word-final diacritic was dropped (`نزلُ` mapped to `نزل`).
Options: A) Map to the nearest kept neighbour (drop boundary marks). B) Extend the span over deleted marks
on both sides until whitespace or a kept character.
Decision: B.
Rationale: AC-4 names the full word. Whitespace is never deleted, so the extension cannot cross a word boundary.
Reversibility: easy — internal to `map_span`.
Confidence: high.
Applied in: fix(S04) commit for review findings

## D-013 — Presigned POST with a size policy for uploads
Date: 2026-11-26 · Slice: S07 · Status: decided · Review: none
Context: The design says "Presigned PUT URL … مع حد الحجم في التوقيع". S3 enforces a size range only in
presigned POST policies (`content-length-range`), not in a PUT signature. S07 Q1.
Options: A) Presigned PUT with a signed Content-Length (size not enforced by S3). B) Presigned POST with a
policy: `content-length-range` and an exact `key` condition. C) Proxy uploads through the API.
Decision: B. The ticket has `url` and `fields` (the signed policy fields). `head()` at ingest (S09) is the
second size gate. The design wording is updated.
Rationale: only B makes S3 reject an oversized upload before it lands. C puts all bytes through the API.
Reversibility: moderate — clients use a POST form instead of a PUT.
Confidence: high.
Applied in: S07 spec commit

## D-014 — Tenant segment in storage keys; contract tests that only real S3 can prove
Date: 2026-11-26 · Slice: S07 · Status: decided · Review: none
Context: S07 says "keys always start with the tenant id" and also gives `incoming/{tenant}/{upload_id}`. A key
cannot both start with the tenant id and begin with a class prefix. Also, AC-1, AC-2 and AC-5 test S3 policy
enforcement and encryption, which the in-memory fake cannot prove.
Options: A) Keys start with the tenant id (`{tenant}/incoming/{upload_id}`). B) Keep the class prefix and
treat the tenant segment as the second path segment. C) Drop the class prefix.
Decision: B. Keys are `incoming/{tenant}/...` and `work/{tenant}/...`; the tenant is always the second segment,
and tenant ids are validated (no `/`, no `..`, non-empty). AC-1, AC-2 and AC-5 run against MinIO only; the
fake runs the shared contract tests (AC-3, AC-6). MinIO is started with a local KMS key so SSE-S3 works.
Rationale: B keeps the spec's key layout and tenant isolation in a single, testable place. Testing the policy
on the fake would prove nothing about S3.
Reversibility: moderate — key layout is stored in the database after S05.
Confidence: medium — the spec's wording is ambiguous; this is the reading that keeps both statements true.
Applied in: S07 test commit

## D-015 — Upload limits, prefix rules and the storage error contract
Date: 2026-11-26 · Slice: S07 · Status: decided · Review: none
Context: The security review found that presigned uploads and prefix deletes accepted values the spec did not
bound: any expiry, any size, any key, and an empty or slash-less prefix that could match other tenants.
The spec gives 15 minutes but no size cap.
Options: A) Validate in each adapter separately. B) Validate in the domain (`storage_keys`) and call from every
adapter and the fake. C) Leave validation to callers.
Decision: B, with these limits: upload size 1 byte to 2 GiB (`MAX_UPLOAD_BYTES`, to revisit with S09 ingest
limits); expiry above zero and at most 15 minutes; keys must be `incoming/{tenant}/{upload}`; delete prefixes
must be non-empty and end with `/`; a negative read start is `ValueError`; a missing key or a read at or
past the end is `PermanentError` on both the fake and S3.
Rationale: one validator means the fake and the adapter cannot drift; the caller cannot widen the policy.
Reversibility: easy — constants and two domain functions.
Confidence: medium on the 2 GiB cap, which is a provisional number.
Applied in: fix(S07) commit for review findings

## D-016 — Persistence model shapes and the config round-trip
Date: 2026-11-26 · Slice: S05 · Status: decided · Review: none
Context: The design lists core columns but not types or identifiers. S05 Q1 is answered here too.
Options: A) Store `pipeline_config` as JSONB and rebuild it through `PipelineConfig`. B) Store the canonical JSON
text. C) Store the flat fields separately.
Decision: A. Ids are server-generated text (uuid4 hex). `Job`, `Media`, `Result` are frozen dataclasses in
`domain/jobs.py`. `segments` is one row per segment with `words` as JSONB (Q1, design table). The round trip
is checked by comparing `canonical_json()` before and after, which is byte-equal (AC-5), though JSONB itself
does not preserve key order.
Rationale: JSONB keeps the config queryable; the canonical form is the contract, not the stored bytes.
Reversibility: moderate — column types are set by migration 0002.
Confidence: high.
Applied in: S05 spec commit

## D-017 — `apply` is keyed by job id without tenant (worker-internal)
Date: 2026-11-26 · Slice: S05 · Status: decided · Review: none
Context: CLAUDE.md and the spec say every query on `jobs` takes `tenant_id`. The spec's `apply(job_id, t, expected,
stage)` signature has no tenant, and its only caller is the worker, which claims jobs by id and has no tenant
context in the lease path.
Options: A) Add `tenant_id` to `apply`. B) Keep the spec signature and document the exception. C) Look the job
up by tenant first, then apply.
Decision: B. `apply` is compare-and-set on the primary key and is called only by workers and the reconciler (S06).
The API surface (`get`, list) always takes `tenant_id`. The exception is recorded here and listed in the BUILD_LOG.
Rationale: A and C add a round trip to every state change for a caller that already holds a trusted job id.
Reversibility: easy — one signature.
Confidence: medium — S08 may want row-level security to enforce the boundary instead.
Applied in: S05 spec commit

## D-018 — Core tables migration; durations in milliseconds; migration test head moves to 0002
Date: 2026-11-26 · Slice: S05 · Status: decided · Review: none
Context: The design table gives `duration_s`. ADR-0003 says integer milliseconds at boundaries. The migration round
trip test pins the head revision, so it must move when 0002 is added (AC-6 requires the round trip to keep passing).
Options: A) `duration_s` as float. B) `duration_ms` as integer (ADR-0003). For the test: edit the head constant
to 0002, or add a second revision check.
Decision: B for durations. The head constant moves to `0002_core_tables`; the test's round-trip logic is unchanged.
Rationale: integer milliseconds keep the time rule from ADR-0003 at the storage boundary. Moving one constant is
the smallest change that keeps the round trip meaningful.
Reversibility: easy before S06 data exists; moderate after.
Confidence: high.
Applied in: S05 migration commit

## D-019 — Review decisions for S05 persistence
Date: 2026-11-26 · Slice: S05 · Status: decided · Review: none
Context: architecture, security and test reviews found tenant leakage in media dedupe, random result ids, lossy
config storage, unchecked reference counts, leaking database errors, and weak contract tests.
Decisions:
- Media is unique per (tenant_id, sha256). A second tenant's identical file is a new row, so no tenant learns that
  another tenant uploaded the same bytes (design: the client never knows a file was uploaded before).
- Result ids are the result key (deterministic, CLAUDE.md). Result claims use an unqualified ON CONFLICT DO NOTHING,
  since both the key and the id are unique.
- `jobs.config_canonical` and `results.config_canonical` store the exact canonical text. Rebuilding from JSONB alone
  changes large floats (1e20 becomes an integer), so the canonical text is the byte-exact source (AC-5). JSONB stays
  for queries.
- `results.ref_count >= 0` is a CHECK constraint. A refused change (unknown id or negative result) is PermanentError.
- SQLAlchemy errors are translated in SqlUnitOfWork: connection failures become TransientError, the rest become
  PermanentError, and the SQL text is never returned to the caller.
- SqlUnitOfWork takes an AsyncEngine; the composition root builds it (CLAUDE.md).
- `apply(..., attempt_count=)` writes the claim count in the same statement, so transition()'s limit can be reached.
- Accepted: result rows are shared across tenants internally (design). S08's API must never return `created`,
  `result_id` or `ref_count` to a client. Recorded as a requirement for S08.
- Accepted: apply stays keyed by job id (D-017).
- S07 correction: the expiry contract test (AC-2) used a one-second policy, which had already expired when the
  control upload went out. It now uses three seconds and sleeps until past `expires_at`. The change was made in the
  S05 branch, so it is noted here and in the S07 BUILD_LOG entry.
Rationale: each item removes a stated invariant violation found by review, or records the design constraint that
remains for a later slice.
Reversibility: moderate — the schema changes are in unmerged migration 0002.
Confidence: high.
Applied in: S05 fix commit

## D-020 — Queue time source, reconciler signature, and out-of-scope fairness
Date: 2026-11-26 · Slice: S06 · Status: decided · Review: none
Context: The spec says lease comparisons use the database's `now()` (clock skew), while the Fake uses the `Clock`
port. The spec signature `Reconciler.run_once(now)` takes an explicit time. S06 Q1 asks about fair scheduling.
Options: A) Compare in SQL with `now()` everywhere; `run_once(now)` records `now` in its report only.
B) Pass `now` into every SQL comparison (clock skew returns).
Decision: A. The Postgres queue compares with `now()` in SQL. The fake compares with the injected Clock. `run_once(now)`
keeps the spec signature; the Postgres reconciler uses DB time for every comparison and echoes `now` in the report.
Q1 (fairness between tenants) is out of scope; a metric in S20 will show when it matters.
Rationale: one source of truth for lease expiry avoids skew between workers and the reconciler.
Reversibility: easy.
Confidence: high.
Applied in: S06 spec commit

## D-021 — `started_at` column and queue fields on Job (migration 0003)
Date: 2026-11-26 · Slice: S06 · Status: decided · Review: none
Context: The claim rule sets `started_at`, which migration 0002 does not have. Migration 0002 is merged, so the change
goes in a new revision. The queue needs `priority` and `run_after` on the domain `Job`, which S05 did not expose.
Options: A) Edit 0002 (already merged; not allowed). B) New migration 0003 adding `started_at`. C) Keep queue fields
out of the domain and pass them separately.
Decision: B. `Job` gains `priority: int = 0` and `run_after: datetime | None = None` with defaults, so existing
callers stay valid. Lease fields (owner, until) stay in the queue layer and are returned as `Lease`.
Rationale: a new revision is the only safe change to a merged schema; defaults keep S05 tests unchanged.
Reversibility: easy before S08 relies on the columns.
Confidence: high.
Applied in: S06 spec commit

## D-022 — S06 review decisions: bounded reclaim, fenced completes, accepted residual risks
Date: 2026-11-26 · Slice: S06 · Status: decided · Review: none
Context: Security, architecture and test reviews of the queue found: validation leases that lapse without limit; a
complete that could land after its lease expired; a transient heartbeat error that cancelled the handler; database
errors leaking from claim; weak chaos and worker tests.
Fixed:
- The claim requires attempt_count < max_attempts (SQL and fake). A validation lease that lapses at the limit is
  poisoned (POISON_JOB); below the limit it is released. The poison decision is the PROCESSING rule of transition().
- A complete requires a live lease (lease_until > now()), in SQL and in the fake.
- A transient heartbeat error is retried on the next beat; only LeaseLostError and JobCancelledError stop the handler.
- claim translates database errors like the other queue methods.
- Tests: worker transient retry, permanent failure, lost lease (handler cancelled, complete never called), heartbeat
  counted; contract tests for a heartbeat after the reconciler and for a future retry; the chaos run now completes
  one abandoned lease per job with a stale owner trying to complete afterwards (the fence refuses all of them).
Accepted, with reasons:
- The claim SQL sets PROCESSING directly. It is the CLAIMED edge of the table, and the contract tests check it.
- Lease durations are float seconds at the SQL boundary. ADR-0003 governs pipeline media time, not lease lengths.
- `complete` does not check the from-state against the transition table. Callers build the Transition from the claimed
  state, and the owner/attempt/liveness predicate fences the write. A future change should pass the from-state.
- Queue methods take no tenant. They are worker-internal, like apply (D-017), and import-linter keeps presentation off
  infrastructure. S08 must not expose them.
- `asyncio.sleep` drives heartbeat timing; the sleep is injectable so unit tests need no real time. The handler
  checkpoint is provided by heartbeat cancellation; a between-stage check arrives with the stages (S10).
- The chaos test uses real 1-second leases; this is the one documented exception to "tests never sleep".
- Fairness and ordering use `seq` (D-021), not created_at, so equal-priority jobs are FIFO inside one transaction.
- A discarded `complete` result (stale write) is not logged yet; logging arrives with S20 observability.
Applied in: S06 review-fix commit

## D-023 — Upload ticket, job creation, and the media placeholder
Date: 2026-11-26 · Slice: S08 · Status: decided · Review: none
Context: A job needs a media row (foreign key), but the file's sha256 is only known after ingest (S09). Creating a job
must still check that the upload object exists (404 otherwise).
Options: A) Create the media row at job creation with sha256 `upload:{upload_id}` as a placeholder, replaced by S09
with the real hash and then deduplicated. B) Add an uploads table in S08. C) Delay job creation until ingest.
Decision: A. The upload id is the media id. Existence is checked with the storage port (`head` on incoming_key).
Rationale: keeps the job row and FK in one transaction; S09 owns the hash. B adds a table with no second use.
Reversibility: easy until S09 runs; the placeholder format is one function.
Confidence: medium.
Applied in: S08 spec commit

## D-024 — Row-level security on jobs: tenant setting, explicit system scope
Date: 2026-11-26 · Slice: S08 · Status: decided · Review: none
Context: The spec wants RLS on `jobs` as a second layer. Workers, the reconciler and the contract tests work across
tenants by design (D-017, D-022), and the table owner bypasses RLS unless FORCE is set.
Options: A) Separate Postgres role for the API with RLS and a worker role without it. B) One role; policy admits a row
when `app.tenant_id` matches it or `app.system = 'on'`; FORCE RLS so the owner is subject to the policy; the
unit of work sets one of the two per transaction with SET LOCAL.
Decision: B. Units of work with a tenant set `app.tenant_id`; units of work without one set `app.system = 'on'`.
A raw connection with neither setting sees no jobs.
Rationale: A needs two roles and two DSNs in CI and locally; B keeps one DSN and tests the policy directly (AC-3).
Reversibility: moderate — policy and the unit-of-work setting.
Confidence: medium — a database role split is the stronger long-term control; revisit at deployment.
Applied in: S08 spec commit

## D-025 — Tenant quota, concurrency limit, idempotency, webhooks, and job progress
Date: 2026-11-26 · Slice: S08 · Status: decided · Review: none
Context: The spec leaves quota numbers, the concurrency limit, the idempotency store, webhooks and `progress` open.
Decisions:
- `tenants.quota_audio_ms` is nullable (NULL = unlimited). Enforced at create against the tenant's media durations.
- `tenants.max_active_jobs` defaults to 5. Active means QUEUED, PENDING_VALIDATION, PROCESSING or RETRY_SCHEDULED.
- Idempotency is a table `idempotency_keys` unique on (tenant_id, key), valid 24 h. A repeat returns the stored
  response with the original status code.
- `webhook_url` is rejected with 422 until S20 persists and delivers webhooks.
- `Job.progress` (0–100) is added to the domain model and mapped from the existing column; default 0.
- Result bodies: GET .../result returns 409 until the job is COMPLETED; after that the JSON body is served once S10/S15
  write transcript versions. Until then a completed job returns 404 with a problem+json reason.
Rationale: each default is the smallest value that does not invent pricing or delivery behaviour.
Reversibility: easy for defaults; moderate for the idempotency table.
Confidence: medium.
Applied in: S08 spec commit

## D-026 — API keys, scopes and problem+json errors
Date: 2026-11-26 · Slice: S08 · Status: decided · Review: none
Context: The spec fixes SHA-256 hashing, two scopes, and RFC 9457 errors. It does not fix the key format or how
errors expose detail.
Decisions:
- A key is `te_` plus 32 URL-safe random characters from `secrets`. Only its SHA-256 hash is stored (api_keys.key_hash,
  unique). A raw key is shown once (seed) and never logged or read back by the system.
- Scopes are `transcribe:read` and `transcribe:write`. Missing or unknown key: 401. Key without the scope: 403.
- Errors are `application/problem+json` with type, title, status and code. The exception message is never returned,
  so internal detail cannot leak; titles are fixed per error.
- The key lookup runs in the system scope because api_keys has no RLS; every later query uses the key's tenant.
- `make seed` creates the local tenant `local` and one key, prints the key once, and writes `.env.local`
  (git-ignored). The system never reads `.env.local` back.
Rationale: hashed keys mean a database read cannot reveal a usable key; fixed titles keep error bodies uniform.
Reversibility: easy — key format and error titles are local.
Confidence: high.
Applied in: S08 auth commit

## D-027 — S08 review decisions: race-free creates, request binding, clock port, residual risks
Date: 2026-11-26 · Slice: S08 · Status: decided · Review: none
Context: security, architecture and test reviews found a race on idempotency and on the active-job limit, an
idempotency key that ignored the request body, an expired key that could not be reused, a clock and an auth lookup
outside their ports, validation errors without problem+json, and weak or missing tests (positive controls, quota,
cross-tenant RLS, the cancel success path).
Fixed:
- Each create takes the tenant row lock (SELECT ... FOR UPDATE), so the idempotency check and the job count run one at a
  time per tenant. The fake lock is a no-op; the fake runs one request at a time.
- An Idempotency-Key stores a SHA-256 of the job-defining fields. Reusing it with a different body is 422
  (idempotency_key_reused). Migration 0004 gained `request_hash`.
- An expired key is released before a new one is written, so a replay after 24 hours creates a new job, as D-025 says.
- Time comes from the Clock port (SystemClock in infrastructure); request deletion and creates use it.
- API key authentication is an application use case (AuthenticateApiKey); presentation only reads the header.
- Pydantic validation errors are problem+json (422, code invalid_request).
- upload_id must be 32 lowercase hex characters (server-generated, D-023).
- Queue claims skip jobs marked for deletion (`deletion_requested_at`).
- The unit of work requires an explicit tenant or None (system); no default scope.
- Cancel builds its response before commit. After commit the tenant setting is gone and RLS hides the row (found by the
  new cancel test).
- Tests: positive controls for every refusal, a concurrent-limit race, cross-tenant RLS, body binding, cancel success
  and a second cancel (409), Retry-After as an integer and absent when terminal, quota with used audio.
Residual, with reasons:
- Quota stays inert until S09 writes real durations (media rows carry 0 until then). The test sets used audio directly.
- `apply` is keyed by job id without tenant (D-017). The API never calls it; only cancel does, after a tenant-scoped read.
- Results are not tenant-scoped yet: the results table has no tenant column and result keys are shared by design
  (D-019). S10 must add tenant scoping before it writes result bodies.
- The API role in tests cannot bypass RLS; production must use a NOBYPASSRLS role (D-024).
- Deletion is a mark only (S21 deletes). The 202 response says the request was recorded, not that data is gone.
Applied in: S08 review-fix commit

## D-028 — S00 partial: build what needs no human data; ADR-0007 provisional
Date: 2026-11-26 · Slice: S00 · Status: decided · Review: requested (R-001)
Context: S00 needs at least 60 min of human-transcribed dev audio (AC-2) and measured CER, WER, RTF and VRAM (AC-3).
The repository has no audio, and an agent cannot be its own ground truth (prompt §5). Dependents such as S12 and S14
still need an engine choice.
Options: A) Block S00 until a person transcribes the hour. B) Build the parts that need no human data (guidelines check,
manifest validator, coverage gate), write ADR-0007 as Provisional on the local profile, mark S00 partial, and continue
with other slices. C) Build a "dev hour" from public audio with machine transcripts (rejected: not ground truth).
Decision: B.
Rationale: prompt §6.2 names this path for S00 on partial data. It keeps the critical path moving and claims no metric
that has not been measured. [D: مجموعة التقييم]
Reversibility: easy — the report and ADR are documents. A measured ADR supersedes ADR-0007.
Confidence: high.
Applied in: S00 commits 5765373 (tests), 16139e2 (validator), 69948a6 (skip-reason fix), docs commits after them.

## D-029 — S09 ingest: media finalize, hand-off on VALIDATED, sandbox on Windows, deferred waiting
Date: 2026-11-26 · Slice: S09 · Status: decided · Review: none
Context: The spec leaves open how ingest writes the media row, how the handler sees its lease, how the sandbox runs
on the Windows host (no cgroups, no non-root), and Q1/Q2. Constraints: `create_job` writes a placeholder sha, and
the media primary key is `id`, so a second insert for the same upload would fail.
Options: A) Insert a second media row (fails on the primary key). B) Add `MediaRepository.finalize`: fill the
upload's own row with the real sha, duration, format and size; if the tenant already has that sha, return that row.
C) Rewrite the upload row in the job.
Decision:
- B. The job keeps `media_id` = upload id. Canonical linking of duplicate media rows is left to S10.
- The handler is `IngestJob(job) -> Transition`. The worker fences `complete()` on the lease, so the handler does not
  need the lease. It returns VALIDATED (→ QUEUED on queue `gpu`), CACHE_HIT (→ COMPLETED) or VALIDATION_FAILED with a
  code. The claim does not move PENDING_VALIDATION to PROCESSING (ADR-0006, claim SQL), so the cpu stage uses the
  PENDING_VALIDATION transitions. The resulting state and queue match the spec's STAGE_HANDOFF.
- Sandbox on this Windows host: argv list with no shell; `-protocol_whitelist file`; minimal environment; ffprobe
  timeout 30 s; ffmpeg timeout 60 s plus half the duration. Playlists (`#EXTM3U`) and concat files (`ffconcat`) are
  refused by magic bytes before any FFmpeg process starts, and the format allow-list refuses HLS and concat after the
  probe. cgroups and the non-root user are not available here: the production CPU worker runs in a Linux container
  that provides them. The gap is recorded here, not silently skipped.
- Q1 (wait for an in-flight duplicate) deferred to S10. S09 completes duplicates from a stored result and otherwise
  runs the GPU stage. Cost: duplicated compute for simultaneous identical uploads. Correctness holds because results
  are keyed; S10's claim at write time decides the winner.
- Q2: channels from the probe are logged as a count, not stored (no column until S13 adds it with a migration).
- Streaming: storage chunks go to the scratch file while the hash updates; `head()` refuses oversize objects before
  download; the streamed total is checked again.
Rationale: [D: دورة الطلب 6–7]، [D: فحص الملفات وعزل FFmpeg]، [D: حدود التشغيل المبدئية]، ADR-0006, ADR-0002.
Reversibility: moderate — `finalize` and the handler contract are used by S10.
Confidence: medium.
Applied in: S09 spec commit (resolved questions), S09 feature commits (see BUILD_LOG).

## D-030 — S09 security review: fixed findings and residual risk
Date: 2026-11-26 · Slice: S09 · Status: decided · Review: none
Context: The security reviewer found four issues in the ingest path. Two were real defects, one is a scope gap that
this host cannot close, and one was a commit-scope mismatch.
Fixed:
- Declared duration was trusted. FFmpeg now runs with `-t` set to the admission limit, and the normalized duration
  and size are checked against the limits before upload. Refusals are TOO_LONG and TOO_LARGE.
- Tool output was read without a cap. The sandbox streams stdout in 64 KiB chunks, kills the tool past 16 MiB, and
  refuses with a permanent error. A test covers the cap. Killing a tool with unread output could hang on Windows,
  so the stop path drains the pipe to EOF and bounds the wait.
- Commit scope: the normalization and hand-off changes were uncommitted when reviewed. They are committed (4c2c2d9),
  and this review covers HEAD.
Residual, not fixed here:
- `-protocol_whitelist file` allows any local path. An MP4 with an external `dref` entry could in principle make the
  demuxer read a host file outside the scratch root. This is not reproduced. The mitigation is process confinement: the
  production CPU worker must run in a container that bind-mounts only the scratch root. This host cannot provide that,
  so the gap is open until the container image exists (S10 make dev, or the deployment slice). A test for the refused
  `dref` must be added with that confinement.
- The ffprobe magic check is a substring match on the first 512 bytes. It can refuse a valid file whose metadata
  contains "ffconcat", and it misses a UTF-8 BOM before `#EXTM3U`. The format allow-list still refuses HLS and concat,
  so this is a nit, not a bypass.
Rationale: [D: فحص الملفات وعزل FFmpeg]; the fixes follow the design's timeouts and limits.
Reversibility: easy — constants and the stop path. The residual needs the container.
Confidence: medium.
Applied in: S09 review-fix commit (see BUILD_LOG).

## D-031 — S09 round-2 review: fixed now, deferred to S10
Date: 2026-11-26 · Slice: S09 · Status: decided · Review: none
Context: The architecture and test reviewers reported "changes needed" on main at 4a08e23.
Fixed now: `-t` clipped output to exactly the limit, so the TOO_LONG check could never fire; the clip is now limit + 1 s
in whole seconds, and the output checks moved to `domain.media_rules.output_error`. `finalize` now runs its update in a
savepoint and re-selects by (tenant, sha256), so a concurrent identical upload no longer raises an untranslated
IntegrityError. Tests added: post-normalize TOO_LONG and TOO_LARGE, probe-error mapping (INVALID_MEDIA,
UNSUPPORTED_FORMAT), and the head() size refusal before download.
Deferred to S10, with the reason:
- The cache-hit `incr_ref` commits before the worker's fenced `complete()`. A lease that expires between the two can
  double-count. The fix is to tie the increment to the fenced completion, or to a per-job reference row. That belongs with
  the lease work, so S10 owns it.
- `IngestJob`, `FfprobeMediaProbe` and `FfmpegNormalizer` are not wired in `main.py`. S10's `make dev` adds the worker
  entry point and its composition root, so the cpu handler is unreachable until then.
- The queue=gpu hand-off is covered by the SQL complete path, not by an S09 test. S10 adds a worker-level assertion.
Rationale: the fixes are local and reversible; the deferred items need the lease and worker changes that S10 makes.
Reversibility: easy for fixes; moderate for the deferred items.
Confidence: medium.
Applied in: S09 round-2 fix commit.

## D-032 — S10 chunk plan: sample_rate in the signature, one chunk per region piece
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: The spec's `plan_chunks` signature omits the sample rate, but `Chunk` carries one, and merge needs it to turn
samples into milliseconds at the boundary (ADR-0003).
Options: A) Read the rate from the media row inside the planner. B) Pass `sample_rate` as a keyword argument. C) Store the
rate in a global. Also: A) pack short regions together across gaps into one chunk. B) one chunk per region piece, cut at
`max_samples`.
Decision: B for the rate (explicit, pure). One chunk per region piece: a region longer than `max_samples` is cut into
consecutive cores, and each short region gets its own chunk.
Rationale: Keeps the planner pure and testable. Packing would hide gaps from the padding rule and change ids when gaps
move. Chunk counts are only a performance concern and can be revisited with a measurement.
Reversibility: easy — the planner is pure and the ids are derived from the plan.
Confidence: medium.
Applied in: S10 chunk commit.

## D-033 — S10 chunk persistence: replace the S05 chunks table, tenant scope without a foreign key
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: Migration 0002 created `chunks` with the S05 shape (state, attempt_count, result_key_s3, no tenant). No code
writes to it, so it is empty. S10 needs tenant, media sha, sample rate and config hash on each chunk. Also, `tenant_id`
on jobs and media has no foreign key to tenants.
Options: A) ALTER the S05 table. B) Drop and recreate it in migration 0005, guarded so it refuses to run if rows exist.
C) Keep the S05 table and add a second one. For tenant scope: A) foreign key to tenants. B) no foreign key, as jobs and
media do; RLS is the tenant boundary.
Decision: B for both. The migration guard raises if `chunks` has rows, so no data is lost silently. The downgrade
restores the S05 shape. The migration head pin in tests/integration/test_migrations.py moves to 0005 (as D-024 did for
0004).
Rationale: A keeps unused columns and needs a data migration nobody can exercise. C leaves two tables with one name.
Without a tenant foreign key, the chunk rows match jobs and media, and RLS holds the boundary.
Reversibility: moderate — the downgrade restores the old shape, but only while the table is empty.
Confidence: high.
Applied in: S10 persistence commit.

## D-034 — S10 processing: partial-failure setting, transcript before completion, gap warnings
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: AC-8 needs a per-tenant flag that requires complete text. The schema has no such column, and adding one is a
separate migration. The worker fences completion, but the transcript write and the completion are separate writes.
Options: A) Add a tenant column now. B) Pass `require_complete_text` as a use-case setting for now, and add the column
with its migration later. For ordering: A) one transaction across the worker's completion and the transcript. B) store the
transcript first, then let the fenced completion run; a crash between the two leaves a stored transcript that the next
attempt overwrites (save_transcript is an upsert). C) store the transcript after completion.
Decision: B for the flag (default: partial text allowed, as the design's default); B for ordering. A chunk that fails
permanently becomes a gap with the warning `chunk_failed:<idx>` on the job. The job's warnings are recorded through
Transition.warnings (S10 part 2). A failed chunk has no stored result; a later attempt retries it.
Rationale: the flag is a configuration decision that can wait for the tenancy work; upserting the transcript makes the
two-step write safe to repeat, and avoids a transaction that spans the worker's fenced completion.
Reversibility: easy — the setting is a constructor argument; the upsert keeps the transcript correct on retry.
Confidence: medium.
Applied in: S10 processing commit.

## D-035 — Plumbing adapters for the local pipeline before S11 and S12
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: `make dev` must run the pipeline end to end on this machine, but speech detection (S11) and a real ASR adapter
(S12) do not exist yet.
Options: A) Wait for S11 and S12. B) Ship plumbing adapters that are labelled as such and make no recognition claim.
C) Ship a fake that invents text. C is rejected: a fabricated transcript could be mistaken for output.
Decision: B. `WholeFileVad` reports one speech region covering the normalized file. It reads only the WAV header through
storage. `PlumbingASR` returns no words. The adapters live under `infrastructure/` and are selected by configuration, not
by a branch in the pipeline. Their transcripts are empty by design, and the demo prints that fact.
Rationale: The plumbing (upload, ingest, chunk plan, fan-out, merge, persist, result) can be proven now. Recognition
quality is not measured until S12 and S16.
Reversibility: easy — both are single adapters behind existing ports.
Confidence: high.
Applied in: S10 plumbing commit.

## D-036 — Worker composition in the composition root; the SQL unit-of-work cast
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: The cpu and gpu handlers (S09 ingest with its planner, S10 process) and the storage client must be built in one
place. `main.py` is the only composition root, so the builders go there. `worker.py` is the entry point: it runs the claim
loop, calls the reconciler between polls, and passes the handler to the worker loop.
Decision: `build_storage`, `build_handlers` and the worker runner are in `main.py` and `worker.py`. Settings come only
from `Settings`. Mypy cannot match `SqlUnitOfWork.__aenter__` (which returns Self) to the `UnitOfWork` protocol's
`__aenter__`, so the composition root wraps it in a documented `cast`. The protocol is not loosened.
Rationale: One composition point keeps the layer rules (import-linter) intact. The cast touches one line and keeps the
port types strict everywhere else.
Reversibility: easy.
Confidence: high.
Applied in: S10 worker commit.

## D-037 — Per-job result references make the cache-hit increment idempotent
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: S09 incremented `ref_count` on a cache hit before the worker's fenced completion (review finding). A lease that
expires after the increment and a re-run of the job would count the same reference twice.
Options: A) Move the increment into the fenced completion SQL. B) A `result_refs` row per (job, result): the increment runs
only when the row is newly inserted, in the same unit of work. C) Leave the double count and rely on reconciliation.
Decision: B. Migration 0006 adds `result_refs` (primary key job_id, tenant_id, result_id) under the RLS policy of jobs.
`add_reference` returns True once per job. A job that never completes keeps its reference, so the count errs high
(never premature deletion).
Rationale: A needs the completion path to know the result; B keeps the increment local to the ingest unit of work and
makes a retry a no-op. C would let a shared result be deleted while in use.
Reversibility: moderate — the table can be dropped only when no job holds a reference.
Confidence: high.
Applied in: S10 result-references commit. Test pin moved to 0006 in tests/integration/test_migrations.py.

## D-038 — Local runtime: compose for Postgres and MinIO, workers as local processes, SSE needs a local KMS key
Date: 2026-11-26 · Slice: S10 · Status: decided · Review: none
Context: `make dev` and `make demo` must run on this Windows machine. The FFmpeg tools and the GPU are on the host. Presigned
POST asks for SSE-S3 (design: server-side encryption), which MinIO refuses without a KMS key. The demo must not read the
API key from .env.local (D-026).
Options: A) Run the workers in containers. B) Run the API and workers as local processes; compose runs only Postgres and
MinIO. For SSE: A) turn encryption off locally. B) set a throwaway local KMS key in compose, as the tests already do.
For the key: A) demo reads .env.local. B) demo reads TE_API_KEY from the environment; the user supplies it from `make seed`.
Decision: B for all three: local processes (so FFmpeg and the GPU are on the host, and the image build waits for the real
ASR), the throwaway KMS key in docker-compose.yml, and TE_API_KEY for the demo. `make dev` runs compose, migrations, the
bucket, the API and both workers, with prefixed logs. `make demo FILE=...` writes out/<job>.json.
Rationale: The pipeline runs on the same machine it will be measured on. SSE stays on, as the design requires, and the
local key is not a secret. The demo never reads what D-026 says the system must not read back.
Reversibility: easy — scripts and one compose variable.
Confidence: medium. Containerised workers (A) remain the production path (ADR-0005); a Linux worker image is a later task.
Applied in: S10 local-runtime commit.

## D-039 — Silero contract: the tone-burst criterion is a region inside a burst, not a count
Date: 2026-11-26 · Slice: S11 · Status: decided · Review: requested (human check with real Arabic speech, R-001)
Context: AC-5 asks that tone bursts are found. Silero is trained on speech. White-noise bursts are not detected at
all. Synthetic 120 Hz harmonic bursts with a syllable-rate envelope give one region that covers part of one burst.
Options: A) Keep "two regions found" and fail. B) Lower the threshold until synthetic bursts pass, which tunes the
detector to the fixture. C) Assert what the adapter guarantees: at least one region, and every region lies inside a
burst.
Decision: C. The test records this. The real speech check happens with the Arabic audio that R-001 will provide.
Rationale: The contract should test the adapter's plumbing and its reporting, not the detector's sensitivity to tones.
Reversibility: easy — one test.
Confidence: medium.
Applied in: S11 adapter commit.

## D-040 — S11 chunking: overlap tiled into cores, VAD parameters from the job, sample-based planner
Date: 2026-11-26 · Slice: S11 · Status: decided · Review: none
Context: Fixed windows overlap by design (1.5 s). The merge rule (S10) needs cores that tile the file, or a word in the
overlap would be kept twice. The spec says VAD parameters come from `PipelineConfig.vad_params`. The S10 planner used
samples, and an existing passing test depends on its constructor.
Decision: (1) `tiles()` splits each overlap at its midpoint: the shared audio becomes padding context, and each sample
belongs to one core. (2) `VadParams.from_mapping` reads `job.config.vad_params`, with defaults for missing keys and
range checks. (3) `PrepareChunks` takes samples (`max_samples`, `pad`, `target_samples`, `overlap_samples`), and the
millisecond `cut_and_merge` stays as the public wrapper. (4) The gaps between regions are the silences that cuts may use.
Also: create_job does not yet write the default VAD parameters into the config; they apply when absent. Adding them to the
result key is a follow-up that changes config canonical JSON for new jobs only.
Rationale: Tiling keeps the midpoint rule valid. Config-sourced parameters are what the result key needs. Samples avoid
rounding loss, as in D-032.
Reversibility: easy.
Confidence: medium.
Applied in: S11 wiring commit.

## D-041 — ASR port shape for S12: identity and capabilities added, call signature kept
Date: 2026-11-26 · Slice: S12 · Status: decided · Review: none
Context: The design lists `DecodeOptions` and a `RawSegment` return for the ASR port. The S10 port returns
`tuple[RawWord, ...]` per chunk and is used by ProcessJob, the fakes and the contract tests.
Options: A) Replace the signature with DecodeOptions and RawSegment now. B) Add `name`, `revision` and
`capabilities` to the Protocol and keep `transcribe(audio_key, chunk, *, language)`. C) Do nothing and read
capabilities from config.
Decision: B. Decoding options (`language`, `temperature=0`) stay as arguments and fixed values inside the adapter.
`DecodeOptions` is deferred until a second engine needs a parameter that cannot be fixed.
Rationale: A changes every caller for no current gain. C leaves provenance and limits unchecked. [D: الـ Ports]
Reversibility: easy (the signature can be widened when a second engine exists).
Confidence: medium.
Applied in: feat(S12) extend ASR port with capabilities.

## D-042 — Hallucination flags are domain functions; propagation to the result is deferred
Date: 2026-11-26 · Slice: S12 · Status: decided · Review: none
Context: AC-5 needs the filter. The design says suspect segments are flagged, never deleted, but the transcript
and result schema do not carry a per-word suspect field yet (S15 and S20 own the result shape).
Options: A) Add a `suspect` column and result field now. B) Ship the pure domain filter with tests; wire it to
the result in a later slice. C) Apply the filter inside the vLLM adapter and drop flagged text.
Decision: B. C is rejected because it deletes text silently. A is deferred because it changes the persisted schema.
Rationale: [D: 4. فلتر الـ Hallucination]. The filter is testable on its own; the wiring needs the result shape.
Q1 parameters (6 words/s, 4-gram, 3 repeats) are the spec's proposals and are tuned in S16.
Reversibility: easy.
Confidence: medium.
Applied in: feat(S12) add hallucination filter. Follow-up: `suspect` on the transcript and result (S15/S16).

## D-043 — Local faster-whisper adapter and the S12 deploy config are deferred
Date: 2026-11-26 · Slice: S12 · Status: decided · Review: requested
Context: D-001 and ADR-0007 name faster-whisper (CTranslate2, FP16) as the local engine, which needs a new
dependency and a model download of several GB. The vLLM model choice is unverified (ADR-0007: Audar and Cohere
not verified on vLLM). The compose service and launch args depend on that model.
Options: A) Add faster-whisper and pull the model now. B) Build the vLLM client and adapter (done) and defer
the faster-whisper adapter and deploy config until the model and the dependency are approved. C) Pick a vLLM
model without verification.
Decision: B. Adding a dependency and pulling model weights are decisions for the owner (CLAUDE.md, AUTOPILOT §5),
and C would fix an unverified runtime into the deploy config.
Rationale: The vLLM adapter already satisfies AC-1 and AC-3 with HTTP mocks. AC-2 (gpu) needs a real server and waits for R-001.
Reversibility: easy.
Confidence: high.
Applied in: none yet. See REVIEW_QUEUE R-003.

## D-044 — S13 routing: domain policy first; singing and the wiring are deferred
Date: 2026-11-26 · Slice: S13 · Status: decided · Review: none
Context: S13 needs a pure routing policy (AC-1, AC-2) and, later, adapters and wiring. Q1 asks for a PROFILING
stage. The stage already exists in `JobStage` (D-005), so Q1 is resolved.
Options: A) Build the policy, adapters and wiring together. B) Build the pure policy now and defer adapters
and wiring until the licenses and dependencies are approved (Q2, R-004). C) Add a singing field to AudioProfile now.
Decision: B. The singing row needs an AudioSet classifier, which the profile does not carry, so it is a follow-up.
Thresholds not fixed by the spec are proposals and are tuned in S16: C50 reverb 10 dB, overlap 0.15, VAD strict 0.7.
Rationale: The policy is testable without models. Adapters need new dependencies and their licenses (Q2), which
are the owner's decision. The wiring for AC-3, AC-5 and AC-6 needs the adapters to be meaningful.
Reversibility: easy. Thresholds change only through a RoutingPolicy version (bumps pipeline_version).
Confidence: medium.
Applied in: test(S13) 9e821d4, feat(S13) 0799aa7. Singing and wiring: follow-up.
## D-045 — S15 cues: the gap rule wins over the minimum duration; reading speed uses the word span
Date: 2026-11-26 · Slice: S15 · Status: decided · Review: none
Context: A cue shorter than 833 ms is extended to that minimum, but it must still keep 80 ms before the next cue.
When the words are close together those two rules cannot both hold. Reading speed (cps) is also measured on the
final display time, which can be shorter than the padded time after the gap clamp.
Options: A) Always extend to the minimum and let cues overlap. B) Gap wins: the cue is shortened to the gap, and
the minimum duration yields only in that case. C) Merge short cues into their neighbours.
Decision: B. The cue end is clamped to (next start − min gap) but never below its last word. Cps is checked on the
word span (last end − first start), which is the shortest possible display time, so the limit holds after the clamp.
Rationale: Overlap breaks players and the gap rule is the stricter readability rule. C changes cue boundaries for a
case the spec does not describe. [D: الترجمات المرئية]
Reversibility: easy (the builder and its test change together).
Confidence: medium. Q1 (17 cps, 42 chars) remains open until a viewer test.
Applied in: S15 cue builder commit.

## D-046 — S15 outputs: format=json keeps the S10 body; profiles and cache
Date: 2026-11-26 · Slice: S15 · Status: decided · Review: none
Context: The result endpoint returns the S10 word-level body for `format=json`, and an existing integration test asserts it.
The design gives only the broadcast subtitle values. `youtube` and `social_vertical` have no values, and the design
asks for a render cache that the spec does not size.
Options: A) Change `format=json` to the canonical body. B) Keep `format=json` as the S10 body and add `format=canonical`
for the canonical JSON. C) Add a render cache now.
Decision: B. Profiles: broadcast = design defaults; youtube = broadcast with a 6 s maximum duration; social_vertical = 24
characters per line and a 4 s maximum duration (both proposals, tuned with a viewer test, S15 Q1). Renders are not cached
yet; they are pure functions of the stored transcript, and the cache is a follow-up.
Rationale: A breaks an existing contract test and a client's body shape. The profile values are the smallest change that
makes the profile observable; the design leaves them open. A cache needs a storage key and invalidation rules that the
spec does not give.
Reversibility: easy (the profile table is one dict; the cache is additive).
Confidence: medium.
Applied in: S15 result-endpoint commit.
## D-047 — S14 digits: Egyptian spoken forms for alignment; the stored word is never changed
Date: 2026-11-26 · Slice: S14 · Status: decided · Review: none
Context: Aligners need the words as they are spoken. Digits in the transcript have no spoken form in the text. S14 Q1
asks whether to verbalize in MSA or Egyptian forms. The audio is Egyptian.
Options: A) MSA forms (خمسون). B) Egyptian forms (خمسين). C) No verbalization; leave digits to the aligner.
Decision: B for 0 to 999 (units, teens, tens, hundreds with the "و" joiner). Numbers from 1000 are spelled digit by digit.
The token map returns every stored token to its spoken words, so the stored text is unchanged.
Rationale: The spec proposes Egyptian forms for Egyptian audio. C would leave digits unaligned. Measure both in S16.
Reversibility: easy (the lexicon is one module; alignment text is recomputed).
Confidence: medium.
Applied in: feat(S14) verbalize_for_alignment, 8ff4c73.

## D-048 — S20 webhooks: two active secrets per tenant during rotation; HTTPS only
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: S20 Q1 asks how tenants rotate webhook secrets. The design does not say. Destinations also need a rule for
the scheme, since the SSRF guard depends on it.
Options: A) One secret; rotation breaks receivers until they update. B) Two active secrets per tenant; both sign while
rotating. C) Plain HTTP allowed for local receivers.
Decision: B for rotation, as the spec proposes. Webhook destinations must be https (C is refused; the guard checks
the scheme and then every resolved address).
Rationale: B lets clients switch without downtime. HTTPS-only keeps the SSRF guard simple and avoids sending signed
bodies in clear text. [D: نقاط النهاية]
Reversibility: easy (the rotation table and the scheme check are small).
Confidence: medium. Storage of the second secret is not built yet (outbox slice).
Applied in: feat(S20) domain webhooks, 749cac1.

## D-049 — S20 storage: outbox rows in the state-change transaction; secrets in a tenant table
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: AC-1 needs an outbox row that exists if and only if the job's state change commits. The design says
webhooks are sent from the outbox but not where the destination and the signing secrets live. D-048 fixed the
rotation rule (two active secrets) and noted that their storage was not built yet.
Options: A) Write the event from the application after the commit (can lose events). B) Write it in the same
transaction from every writer of a terminal state (apply, the fenced worker complete, the reconciler's poison
update). C) A trigger on jobs. Destination: D1) a column on jobs, from the create request (design: webhook_url) or
D2) a tenant setting. Secrets: E1) a table per tenant, plaintext, RLS as on other tenant tables, or E2) encrypted at
rest with a key from the environment.
Decision: B for the events. The destination is a nullable jobs.webhook_url copied into the outbox payload when the
event is written, so the publisher never reads jobs. Secrets are E1 (plaintext HMAC keys in webhook_secrets,
tenant RLS, the publisher reads at most two active rows).
Rationale: B is the only option where the event and the state change share one transaction, which AC-1 requires.
C would hide the rule in SQL the tests cannot see. The copy of the destination freezes it at completion, which is
what the client asked for. E1 is the smallest change that matches D-048. An HMAC key cannot be hashed, and E2 needs
a key-management decision that the design does not make; it is recorded as a follow-up for S21 (secrets at rest).
Reversibility: moderate — the outbox columns and the table are small, but rows already written keep their payload.
Confidence: medium. Encryption of secrets at rest is open (see follow-ups in the S20 build log).
Applied in: 898add2 (outbox write, migration 0007).

## D-050 — S20 test correction: the webhook refusal test uses an http URL
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: `test_webhook_is_refused_until_s20` created a job with an https webhook URL and expected a refusal
because webhooks arrived with S20. Under D-048 https webhooks are the supported case, so that premise is wrong.
Options: A) Delete the test. B) Keep the same expectation for a URL that stays refused (http). C) Change the
expectation to "accepted" before the feature exists, which would fail.
Decision: B. The URL becomes http://; the refusal stays. The https acceptance and the http error class follow in
the next feat commit, which also updates this test's expected error.
Rationale: keeps the commit green and keeps the test's refusal check; the change is limited to the URL.
Reversibility: easy.
Confidence: high.
Applied in: fix(S20) commit following bfe0364.

## D-051 — S20 webhook URL at job creation: https accepted, other URLs get a dedicated error
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: create_job refused every webhook_url as UnsupportedFeatureError until S20. S20 makes https webhooks
supported. The refusal for other URLs still needs an error.
Options: A) Keep UnsupportedFeatureError for http (the message "not available yet" is wrong for a bad value). B) A
dedicated InvalidWebhookUrlError, 422, code invalid_webhook_url. C) Accept any URL and reject at send time.
Decision: B. The scheme and host are checked at creation; the address (DNS, private ranges) is checked at send time
by the publisher (AC-3).
Rationale: the client gets a precise error for a bad value; C would store URLs that can never be sent. The
creation check is syntactic, so it needs no DNS call in the request path.
Reversibility: easy.
Confidence: high.
Applied in: feat(S20) accept https webhook URLs at job creation.

## D-052 — S20 observability: stdlib JSON logs, prometheus_client metrics, spans as log records
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: the spec asks for JSON logs, metrics, and one trace span per stage linked by job_id. structlog and
prometheus-client are already runtime dependencies (pyproject). OpenTelemetry is not a dependency yet.
Options: A) structlog everywhere. B) Stdlib logging with a JSON formatter; prometheus_client for metrics; spans
emitted as span.start/span.end log records. C) Add opentelemetry-api/sdk now and export spans.
Decision: B. Application code uses logging.getLogger; the JSON formatter lives in infrastructure and is installed by
the entry point. Spans are a context manager that logs start and end with job_id, stage, status, duration_ms.
Rationale: no new dependency, and the application layer keeps no logging-library import beyond stdlib. Exporting
spans needs an OpenTelemetry decision (licence Apache-2.0, a collector in deployment), which the design leaves to
deployment; the log-based span keeps the call shape so an exporter can replace the sink later.
Reversibility: easy — the formatter and the span helper are small and local.
Confidence: medium. Spans are not yet wired into the pipeline stages (follow-up); the helper is tested.
Applied in: feat(S20) JSON logs, metrics and stage spans.

## D-053 — S20 delivery: pinned addresses, global-only ranges, leased outbox rows, httpx logs quiet
Date: 2026-11-26 · Slice: S20 · Status: decided · Review: none
Context: the architecture and security reviews found that the SSRF check and the connect could resolve the name
differently (DNS rebinding). The range check missed CGNAT, the Alibaba metadata address and NAT64-embedded IPv4.
Two publishers could both send the same row, because SKIP LOCKED ends at commit. httpx logs each request URL at
INFO, which can carry a token in the webhook query.
Options: A) Re-check the peer address after connect (complex with pooled connections). B) Pin the verified address
and send Host and SNI for the original name. C) Lease the outbox row with owner-fenced writes. D) Allow only
is_global addresses, check embedded IPv4, and allow port 443 only. E) Quiet httpx and httpcore to WARNING.
Decision: B, C, D, E. The publisher resolves once through a Resolver port, checks, and sends to the first verified
address. Rows are leased (lease_owner, lease_until), and every write names the owner.
Rationale: B closes the rebinding window without pooled-connection tricks; the TLS name check still uses the
destination. C makes each lease a single attempt. D and E fix the reviewed risks directly.
Reversibility: easy (code, and migration 0007, which is not on main yet).
Confidence: medium. Not verified: the httpx SNI extension against a live TLS server (only MockTransport is tested).
Applied in: fix(S20) delivery hardening.

## D-054 — Autopilot blocked: partial dependencies do not unblock dependents
Date: 2026-11-26 · Slice: — · Status: decided · Review: requested
Context: AUTOPILOT 2.1 lets a dependent start only when its dependencies are done, except S00 on partial. Every
remaining slice now depends on a partial slice (S12, S14, S15, and through them S16 to S22). The missing parts are
owner decisions (R-003 model and dependency, R-004 licences, R-005 aligner and viewer test).
Options: A) Let dependents proceed on partial dependencies, recording what is missing. B) Keep the rule and stop
until R-003/R-004/R-005 are decided. C) Build the dependents on fakes as if the dependency were done.
Decision: B for now. The run stops with state.status = blocked. Option A is the owner's call, since it changes a
rule in AUTOPILOT 2.1.
Rationale: Option C would hide missing behaviour behind fakes. Option A changes the process itself, which the owner sets.
Reversibility: easy (one state edit).
Confidence: medium.
Applied in: docs(autopilot) blocked state commit.

## D-055 — Dependents may start on partial dependencies; supersedes D-054
Date: 2026-11-26 · Slice: — · Status: decided · Review: none
Context: D-054 blocked the run because every remaining slice depends on a partial one. The owner chose to allow it.
Options: A) Keep the block (D-054). B) Allow dependents on partial dependencies, recording each missing piece.
C) Build dependents on fakes that stand in for the missing piece without recording it.
Decision: B. A dependent may start when its dependency is partial. The dependent's BUILD_LOG entry must list which
dependency pieces are missing and why the dependent does not need them. Items stay in REVIEW_QUEUE.
Rationale: the missing pieces are owner decisions (R-003, R-004, R-005); waiting blocks all remaining work.
Reversibility: easy (one rule change).
Confidence: medium.
Applied in: docs(repo) resume commit.

## D-056 — S17 default diarizer: none wired yet; port and fake first
Date: 2026-11-26 · Slice: S17 · Status: decided · Review: requested (R-008)
Context: S17 Q1 asks whether pyannote or Sortformer is the default. The DER comparison needs the S16 dev set, which
does not exist (R-001). Both models need terms accepted on their hosts (pyannote gated, Sortformer under NVIDIA NeMo).
Options: A) Install pyannote now with a token (not allowed without owner approval). B) Install Sortformer via NeMo
(a large new dependency, licence check open). C) Build the port, the pure assignment and a fake; wire the job to
the port; leave the default unset until the owner approves a model.
Decision: C. The default is unset. No adapter is added in this run.
Rationale: AUTOPILOT §5 bars accepting terms and entering tokens. The DER comparison cannot run without human
reference data. The port and wiring are reversible and let S17's behaviour be tested now.
Reversibility: easy (adapters are added behind the port later).
Confidence: high for not installing; medium for the port shape.
Applied in: docs(S17) resolve Q1.

## D-057 — S18 scope: pure RAG domain first; FTS v1; models deferred (R-009)
Date: 2026-11-26 · Slice: S18 · Status: decided · Review: requested (R-009)
Context: S18 Q1 (BM25 in Postgres), Q2 (embedding and reranker models) and Q3 (parent level before chapters).
Options: Q1: A) built-in FTS (proposed), B) extension, C) OpenSearch. Q2: A) pick a model now, B) defer the model, the
adapter waits. Q3: A) fixed windows on speaker turns (proposed), B) wait for S19.
Decision: Q1 A (FTS behind SearchIndex, recall compared in S16 later). Q2 B: the Embedder and reranker ports are built
with a fake; the model choice and its download need owner approval (R-009). Q3 A, parent level in a later step.
Rationale: FTS needs no new dependency. A model download and its terms are owner decisions. Fixed windows need no
chapters.
Reversibility: easy (behind ports).
Confidence: medium.
Applied in: docs(S18) resolve Q1 to Q3.

## D-058 — S19 enrichment: no LLM wired; pure analytics and snapping first
Date: 2026-11-27 · Slice: S19 · Status: decided · Review: requested (R-010)
Context: S19 Q1 asks which LLM and where it runs. A hosted model would send transcripts outside the cluster, which
the rules forbid without the owner's decision (AUTOPILOT §5; privacy). A local model needs a download and terms.
Options: A) Hosted API. B) Local model now. C) Port and fake; pure analytics and snapping now; local model later.
Decision: C. Enrichment runs on the fake enricher. Speaker analytics, chapter snapping and entity verification are
pure domain logic and need no model.
Rationale: transcripts are private data; no hosted call is made without approval. The rules that matter (snapping,
verification, isolation) do not depend on the model.
Reversibility: easy (an adapter behind the port).
Confidence: high.
Applied in: docs(S19) resolve Q1.

## D-059 — S21 deletion: storage first, then one database transaction; legal review open (R-011)
Date: 2026-11-27 · Slice: S21 · Status: decided · Review: requested (R-011)
Context: S21 deletes everything a job owns, keeps shared results until the last owner goes, and sweeps expired
audio. Q1 is a legal question (Law No. 151 of 2020 and where GPUs run); the autopilot cannot decide it.
Options: A) Database first, then storage: a failed storage delete leaves orphan objects after the rows are gone.
B) Storage first (idempotent), then the rows in one transaction; a retry is safe. C) Wait for legal review.
Decision: B for engineering. A result is released only when its ref_count is 0 and no job still points at it. The
original upload is deleted only when no other job or result uses its media row. No region pinning is built.
Known window: a new job for the same media created during a delete can race the plan; the apply re-checks inside
its transaction and reports it, but the object is already gone. Recorded as a follow-up.
Rationale: B makes every failure retryable. C would block the engineering work; the legal answer changes only
residency, not the deletion mechanics.
Reversibility: moderate (schema changes for audit and consent).
Confidence: medium.
Applied in: docs(S21) resolve Q1.

## D-060 — S21 review fixes: per-job isolation, system-scope ownership checks, audio not kept by results
Date: 2026-11-27 · Slice: S21 · Status: decided · Supersedes: the results part of D-059 · Review: requested (R-011)
Context: the S21 security review found that one failing job stopped the runner and the sweep for every later job,
that ownership checks ran under tenant RLS (other tenants' jobs were invisible), and that a cached result kept
the producer's original upload, so DELETE left the audio in place for shared results.
Options: A) Keep the blanket runner; log and retry later. B) Isolate each job; log its id and error class; leave it
pending. For ownership: A) keep RLS scope. B) run the checks under system scope in the same transaction. For audio:
A) keep the upload while any result points at it. B) decouple: a cached transcript does not need the audio; clear
results.media_id and delete the upload when no job uses it.
Decision: B for all three. Migration 0008 (unmerged) makes results.media_id nullable and adds a CHECK on
retention_days (1 to 3650).
Rationale: a poison job must not block deletion of every later job (safety and data). Tenant RLS must not hide
references that protect shared rows. The original upload is the most sensitive object; the cached transcript
does not need it. Legal review (R-011) still applies before production.
Reversibility: moderate (schema nullability, two code paths).
Confidence: medium.
Known follow-ups, not changed here: cross-tenant reuse of results by file sha256 with no isolation scope
(pre-existing, D-007; needs a decision on isolation); the expire_audio path leaves a media row whose object is gone
(harmless, cleaned at delete); no embeddings table yet, so the deletion path has nothing to remove for embeddings.
Applied in: 0709541 (isolation), 76ca636 (ownership and audio).

## D-061 — S22 scope: pure edit, diff and manifest first; versions and aligner behind ports
Date: 2026-11-27 · Slice: S22 · Status: decided · Review: none
Context: S22 Q1 asks which client builds the editor. The backend only needs to save and diff. The design needs a
versioned transcript store (not yet in SQL), the S14 aligner (R-005, not built) and the API layer.
Options: A) Build the SQL version store and the endpoint now. B) Build the pure logic and the use case on in-memory
ports and fakes; defer the SQL store, the endpoint and the real aligner. C) Wait for the editor decision.
Decision: Q1 is left to the owner (not a backend decision). B: the edit model, timing merge, diff, consent manifest,
and SaveCorrection run on fakes. The SQL version store, the endpoint and the aligner adapter are follow-ups.
Rationale: the consent gate and the diff rules are the parts that must be right; the storage and API can follow the
ports without changing the rules.
Reversibility: easy.
Confidence: medium.
Applied in: docs(S22) resolve Q1.

## D-062 — S22 versions over HTTP: SQL store with the primary key as the guard; no invented alignment
Date: 2026-11-27 · Slice: S22 · Status: decided · Review: requested (R-005)
Context: S22 needs a versioned transcript store, an endpoint, and alignment for changed words. Completed jobs
store only merged words, and no aligner adapter exists (R-005).
Options: A) Store canonical JSON per version, the primary key as the concurrency guard, the ASR version built on
first read. B) A mutable transcript row with a version counter (lost-update risk). C) Invent word times when no
aligner is configured.
Decision: A. An edit that needs new word times is refused with 503 (alignment_unavailable) until an aligner is
configured. Speaker-only and no-timing changes still save. Other integrity errors are permanent, not conflicts.
A deleted job's versions are deleted with the job, and a save on a deleted job reads and writes nothing (S21).
Rationale: the primary key makes a lost update impossible without a lock; refusing beats inventing times, which
would corrupt the training data (S22 AC-1).
Reversibility: moderate (migration 0009 is on main).
Confidence: medium.
Applied in: 47312d7, f3968a5, 236cba7.

## D-063 — Local ASR: openai/whisper-large-v3-turbo through transformers, from the local cache
Date: 2026-11-27 · Slice: S12 (R-003) · Status: decided · Review: requested (production model, R-003 part b)
Context: R-003 asked for faster-whisper and a production model. The owner asked for the best local choice.
The machine has no converted CTranslate2 turbo model, but the Hugging Face cache (D:\AI\Models) holds
openai/whisper-large-v3-turbo with full weights, and the cache has no faster-whisper turbo conversion.
Options: A) faster-whisper with a CTranslate2 conversion of turbo (needs a conversion run and the faster-whisper
dependency). B) whisper-large-v3-turbo through transformers, FP16 on CUDA and FP32 on CPU, from the local cache.
C) faster-whisper-base (142 MB, CTranslate2, already converted), a weaker model.
Decision: B. The adapter reads the model offline (local_files_only); it never downloads. Settings TE_ASR_ENGINE
(default whisper_local), TE_ASR_MODEL_ID and TE_ASR_DEVICE select it. The plumbing engine stays selectable.
Rationale: turbo is the best Whisper model present with complete weights, and it covers Arabic. A conversion (A)
adds a step with no gain in accuracy. Measured on this machine (smoke test, two real Arabic clips of 2 s and 2.6 s,
CPU FP32): model load 8 s after the first cache read, about 14 s of inference per clip. That is not real-time; the
CUDA path (FP16, Quadro RTX 5000) is the fast path and needs a CUDA torch build, which is not installed (follow-up).
Licences: transformers 5.24.1 is Apache-2.0 (read from its package metadata). Whisper weights are MIT as published
upstream; the cache holds no model card to confirm it, so this is recorded as unverified in the cache.
Dependency: transformers added to the project (uv add). torch stays the optional ml extra; the adapter imports torch
and transformers lazily so CI, which does not install torch, still imports the module.
Reversibility: easy (the adapter is behind the ASR port; the setting selects it).
Confidence: medium. Accuracy is not measured: R-001 (the human reference hour) is still open, so only the
smoke output is known, not a word error rate.
Applied in: feat/R003-local-asr (adapter, settings, window refactor, tests).

## D-064 — S10 fence: a job completes only after its chunk plan is prepared
Date: 2026-11-27 · Slice: S10 · Status: decided · Review: none
Context: a local demo produced COMPLETED jobs with empty transcripts. A cpu ingest that outlives its lease can be
overtaken by the GPU stage, which then completes the job before the chunk plan is written.
Options: A) Fence the plan write to the lease. B) Refuse to complete a job whose plan is missing and not prepared,
and retry. C) Leave it.
Decision: B. The plan write and a prepared mark (jobs.prepared_at, migration 0010) commit in one transaction. An
empty plan for a silent file is prepared too, so silence still completes. ProcessJob raises TransientError while the
job is not prepared.
Rationale: B needs no change to the lease protocol and fails safe: the job is retried, never completed empty.
Reversibility: easy (one column, one check).
Confidence: high.
Applied in: 6723249.

## D-065 — S10 chunk ids are job-scoped; the AC-4 golden value changes
Date: 2026-11-27 · Slice: S10 · Status: decided · Review: none
Context: chunk ids were a hash of the media sha, config and sample range, with no job id. The same audio processed by
a second job (a re-upload of the same file) produced the same ids. The chunk table's primary key is the chunk id, so
the second job's chunk rows were dropped by ON CONFLICT DO NOTHING, and its plan read returned no chunks: a
COMPLETED job with an empty transcript. This is why every re-run of the same clip came back empty.
Options: A) Job-scoped ids (the job id joins the hash). B) Primary key on (job id, chunk id) with a foreign key change.
C) Keep content ids and key the plan by content.
Decision: A. chunk_id(job_id, media_sha256, config_hash, idx, start, end). The golden value in the AC-4 test changes
to the new formula, because the id format changed by design. Re-runs of the same job still give the same ids, so
resume is unchanged.
Rationale: A is the smallest change that makes the id unique per job; B changes the key of chunk_results too.
Reversibility: easy (ids are recomputed; no stored ids outlive a plan).
Confidence: high.
Applied in: the feat(S10) job-scoped chunk id commit.
