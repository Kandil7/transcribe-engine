---
name: extract-spec
description: Draft or refresh a slice spec (specs/SXX-*.md) from the design document. Use when starting a slice whose spec is missing, outdated, or contradicts docs/design.md.
argument-hint: SXX
---
Extract the spec for slice $ARGUMENTS from the design document. Work in plan mode: read, then write one file.

## Inputs (read only these)
1. `specs/README.md` — find the row for $ARGUMENTS: title, dependencies, design sections.
2. The listed sections of `docs/design.md` only (grep the Arabic headings; do not read the whole file).
3. `docs/adr/` files whose title matches the slice topic.
4. The **Interfaces** section of every spec this slice depends on (not their full text).
5. `specs/_TEMPLATE.md`.

## Rules
- Every requirement sentence in the listed design sections must land in exactly one place:
  an acceptance criterion, "Out of scope (→ SYY)", or "Open questions". Nothing silently dropped.
- Tag each acceptance criterion with its source: `[D: <Arabic heading>]` or `[ADR-000N]`.
- Never invent numbers, thresholds or behaviors. If the design doc is silent or two sections
  disagree, write an Open question with both readings and a proposed default. Do not pick silently.
- Acceptance criteria must be testable: name the test, its type (unit / contract / integration),
  and the observable result. "Works correctly" is not a criterion.
- Interfaces use real Python signatures with domain types. Respect CLAUDE.md layer rules.
- Commit plan: 4–9 steps, each one small, each leaving `make check` green
  (new tests start as `xfail(strict=True, reason="$ARGUMENTS")`).
- Keep the spec under ~150 lines. Link to design sections instead of copying prose.

## Output
1. Write `specs/$ARGUMENTS-<slug>.md` from the template.
2. Run the `spec-reviewer` subagent on it. Fix gaps it reports that affect coverage or testability.
3. Print: coverage table summary (requirements → AC / out of scope / open question counts),
   and the open questions. Stop there: a human answers open questions before implementation.
