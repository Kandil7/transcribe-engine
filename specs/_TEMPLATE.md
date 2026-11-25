# SXX — <Title>

| | |
|---|---|
| Phase | 0–5 (from design doc "المراحل") |
| Depends on | SYY, SZZ (must be merged to main) |
| Branch | `feat/SXX-<slug>` |
| Design sections | `## <Arabic heading>` › `### <Arabic subheading>` |
| ADRs | 000N |

## Goal
One or two sentences: what exists after this slice that did not exist before, and how we know.

## Scope
- In: …
- Out (→ SYY): …

## Interfaces
```python
# Real signatures. Domain types only. These are what later slices may depend on.
```

## Files
- `src/transcribe_engine/...` — new / changed, one line each
- `tests/...`

## Rules
Behavior the code must follow, each traceable: `[D: <heading>]` or `[ADR-000N]`.

## Edge cases
- …

## Acceptance criteria
Each AC: id, source tag, test name, type (unit / contract / integration / gpu / eval), observable result.
- **AC-1** `[D: …]` — `tests/unit/.../test_x.py::test_y` (unit): given …, when …, then …

## Verification
```bash
make check
make itest   # if infrastructure is touched
```

## Commit plan
Each step keeps `make check` green. New tests start as `xfail(strict=True, reason="SXX")`.
1. `docs(SXX): add spec`
2. `test(SXX): add acceptance tests (xfail)`
3. `feat(SXX): …`
4. …
n. `docs(SXX): update design doc / ADR` (only if something changed)

## Open questions
- [ ] Q1 — <question>. Reading A: … Reading B: … Proposed default: … (resolved by: name, date)
