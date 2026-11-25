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
