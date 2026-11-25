---
name: implement-slice
description: Implement one approved slice spec end to end on its own branch, committing after every step of the spec's commit plan.
argument-hint: SXX
disable-model-invocation: true
---
Implement slice $ARGUMENTS. Follow CONTRIBUTING.md exactly.

## 0. Preconditions (stop and report if any fails)
- `specs/$ARGUMENTS-*.md` exists and its **Open questions** section is empty or marked resolved.
- Every slice in its `Depends on` line is merged to `main` (`git log main --oneline | grep "(SYY)"`).
- Working tree is clean.

## 1. Branch
```bash
git fetch origin && git switch main && git pull --ff-only
git switch -c feat/$ARGUMENTS-<slug-from-spec-filename>
```
If the spec file is new or changed, commit it first: `docs($ARGUMENTS): add spec`.
Push and open a draft PR: `gh pr create --draft --fill --title "$ARGUMENTS: <spec title>"`.

## 2. Plan (no edits)
Read the spec, the design sections it cites, and the files under **Files**. Write a short plan that
maps each commit-plan step to files and tests. Show it and wait for approval.

## 3. Tests first
Write every acceptance test named in the spec, marked
`@pytest.mark.xfail(strict=True, reason="$ARGUMENTS")`. Run `make check` (must pass: they xfail).
Commit: `test($ARGUMENTS): add acceptance tests (xfail)`.

## 4. One commit per step
For each remaining step in the spec's commit plan, in order:
1. Implement only that step.
2. Remove the `xfail` marker from the tests this step makes pass. Never edit test assertions.
3. `make check` (the Stop hook enforces it). For infra steps also run `make itest`.
4. Commit with the exact message from the commit plan. Body: one line on *why*, plus
   `Spec: specs/$ARGUMENTS-....md`.
5. Push.

## 5. Review
1. Run the `architecture-reviewer` subagent on `git diff main...HEAD`.
2. If the slice touches uploads, FFmpeg, auth, SQL or storage, also run `security-reviewer`.
3. Run the `test-reviewer` subagent.
4. Fix findings that affect correctness or the spec. Commit: `fix($ARGUMENTS): address review findings`.
   List the rest in the PR description as "not addressed (reason)".

## 6. Close
- `grep -rn 'reason="$ARGUMENTS"' tests` returns nothing.
- Any decision not in the spec → ADR via `/write-adr`, committed as `docs(adr): ...`.
- Update the PR description from the template with evidence, then `gh pr ready`.
- Report: commits made, AC → test mapping, open follow-ups.
