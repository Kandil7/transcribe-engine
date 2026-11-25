# Contributing: branches, commits, PRs

Short version for humans and Claude Code. The Arabic walkthrough is `docs/WORKFLOW.ar.md`.

## Branches
| Branch | From | Purpose | Lifetime |
|---|---|---|---|
| `main` | — | Always green, always deployable. Protected: PR + CI required, linear history, no force push. | forever |
| `feat/SXX-<slug>` | `main` | One slice from `specs/`. Name matches the spec file. | 1–3 days |
| `spike/SXX-<slug>` | `main` | Experiments (S00). May merge only docs/notebooks/ADRs. | days |
| `fix/<short>` | `main` | Bug fix outside any slice. Scope `repo` or the owning slice id. | hours |
| `docs/<short>` | `main` | Design doc / ADR changes not tied to a slice. | hours |

- One slice per branch. Never two slices on one branch, never one slice across branches.
- Start a slice only when every slice in its `Depends on` is merged.
- Rebase on `main` at least daily: `git fetch origin && git rebase origin/main`, then
  `git push --force-with-lease` (plain `--force` is blocked by the hook).
- Parallel slices: one git worktree each: `git worktree add ../te-S15 -b feat/S15-canonical-transcript-renderers`.

## Commits: one per step
Format (checked by `scripts/check_commit_msg.py` locally and in CI):
```
type(scope): summary in imperative, ≤ 72 chars

Why this step exists (one or two lines).

Spec: specs/SXX-<slug>.md
```
- `type`: feat, fix, test, refactor, docs, chore, perf, build, ci, revert, spike
- `scope`: the slice id (`S06`), or `repo`, `ci`, `deps`, `docs`, `eval`, `adr`

Every slice follows the same sequence, taken from its spec's **Commit plan**:
1. `docs(SXX): add spec` — first commit; open a **draft PR** right after it.
2. `test(SXX): add acceptance tests (xfail)` — every AC test, marked `xfail(strict=True, reason="SXX")`.
3. `feat(SXX): <step>` — one commit per plan step; remove the xfail markers this step satisfies.
4. `refactor(SXX): …` — optional, behavior unchanged, tests untouched.
5. `docs(adr): NNNN …` / `docs(SXX): update design doc` — only if a decision changed.
6. `fix(SXX): address review findings` — after the reviewer subagents.

Rules:
- **Every commit passes `make check`.** That is why new tests start as strict xfail: the suite stays
  green, and `xfail_strict` fails the build the moment a test passes while still marked.
- Never edit an existing assertion to make it pass. A wrong test gets its own commit:
  `fix(SXX): correct AC-3 test expectation` with the reason in the body.
- No commits on `main` (hook-blocked). No `--no-verify` (hook-blocked).
- Small commits: if the summary needs "and", split it.

## Pull requests
- Title: `SXX: <spec title>`. Body from `.github/pull_request_template.md`.
- Draft after the spec commit; ready when: all ACs have passing tests, no `reason="SXX"` xfails remain,
  reviewer findings addressed or listed, CI green.
- Merge method: **Rebase and merge** only. Step commits land on `main` as-is, each green, so
  `git bisect` works and the history reads as the spec's commit plan.
- Delete the branch after merge (automatic).

## Releases
- Tag the end of each roadmap phase on `main`: `v0.<phase>.0` (e.g. `v0.2.0` after S10).
- Changelog generated from commit types (`feat`, `fix`, `perf`) grouped by slice scope.
