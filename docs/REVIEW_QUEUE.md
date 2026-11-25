# Review queue — needs a human

The autopilot never waits on these. It records them, works around them with a stub, fake or the most
reversible option, and continues. Clear an item by answering it here and, if it changes a decision,
asking the next run to supersede the decision (add a line under "Instructions for the next run").

| ID | Date | Slice | What is needed | Why the agent cannot do it | Workaround in place | Decision |
|---|---|---|---|---|---|---|
| R-001 | — | S00 | ≥ 1 h of Egyptian audio transcribed by a person, per `evaluation/guidelines.ar.md` | an agent cannot be its own ground truth; consent required | ADR-0007 provisional, engine chosen by local profile | — |
| R-002 | 2026-11-25 | S01 | Approve `git push --force-with-lease=feat/S01-foundation:b776f35… origin feat/S01-foundation`, or tell the run where to push. The remote branch carries duplicate bootstrap/S00 commits and a replayed `prompt/AUTOPILOT.md`; the local branch is main + 4 clean S01 commits. Old tip kept at PR #1 head. | The permission classifier denied the force push (destructive on a remote branch another run updated). | Local branch only; no CI for S01 yet | — |

## Instructions for the next run
- R-002 pending: once approved, push S01 with the lease above, then open/merge PR #1 (rebase-merge).
<!-- Write instructions here, e.g. "R-001 done: data in data/eval/; finish S00 and revisit D-001". -->
