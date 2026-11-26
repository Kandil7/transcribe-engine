# Review queue — needs a human

The autopilot never waits on these. It records them, works around them with a stub, fake or the most
reversible option, and continues. Clear an item by answering it here and, if it changes a decision,
asking the next run to supersede the decision (add a line under "Instructions for the next run").

| ID | Date | Slice | What is needed | Why the agent cannot do it | Workaround in place | Decision |
|---|---|---|---|---|---|---|
| R-001 | — | S00 | ≥ 1 h of Egyptian audio transcribed by a person, per `evaluation/guidelines.ar.md` | an agent cannot be its own ground truth; consent required | ADR-0007 provisional, engine chosen by local profile | — |
| R-002 (resolved 2026-11-25: force-with-lease to be18a97, PR #1 rebase-merged to 2985206) | 2026-11-25 | S01 | Approve `git push --force-with-lease=feat/S01-foundation:b776f35… origin feat/S01-foundation`, or tell the run where to push. The remote branch carries duplicate bootstrap/S00 commits and a replayed `prompt/AUTOPILOT.md`; the local branch is main + 4 clean S01 commits. Old tip kept at PR #1 head. | The permission classifier denied the force push (destructive on a remote branch another run updated). | Local branch only; no CI for S01 yet | — |
| R-003 | 2026-11-26 | S12 | (a) approve adding `faster-whisper` (MIT) as the local-gpu engine dependency and the download of its FP16 model weights (several GB, from the public Hugging Face hub); (b) name the vLLM production model to serve (Audar or Cohere, ADR-0007) so the deploy config can be written | Adding a dependency and pulling weights are the owner's decisions; the production model choice is unverified (ADR-0007) | vLLM adapter built and tested with HTTP mocks; no local ASR yet, so the local demo still uses plumbing ASR (D-035) | D-043 |
| R-004 | 2026-11-26 | S13 | (a) check and approve the licenses of Brouhaha, DNSMOS, DeepFilterNet and Demucs for commercial use (spec Q2), then approve their dependencies and model weights; (b) decide whether the AudioSet singing classifier is in scope | Licenses and dependencies are the owner's decision (AUTOPILOT §5). The singing classifier is a new model | Routing policy built and tested as pure domain; adapters and wiring not started | D-044 |
| R-005 | 2026-11-26 | S14, S15 | (a) approve the Arabic wav2vec2 aligner model and its dependencies (torch, transformers, the model weights from the public hub, license to check); (b) a viewer test to confirm reading speed 17 cps and 42 characters per line for Arabic subtitles (S15 Q1) | Model and dependency choices and licences are the owner decision; a viewer test needs people | S14: verbalizer built and tested. Aligner port, adapter and wiring not started. S15: profile values are proposals (D-046) | D-046, D-047 |
| R-006 | 2026-11-26 | S20 | Run `promtool test rules deploy/observability/alerts_test.yml` locally, or approve executing the downloaded promtool 2.53.0 binary on this machine | The permission system denied running the downloaded binary, so AC-7 cannot be checked here | CI job `alerts` installs the same pinned release and runs `promtool check rules` and `promtool test rules` on every PR | — |
| R-008 | 2026-11-26 | S17 | (a) choose the default diarizer (pyannote or Sortformer, spec Q1 and D-056) and accept its model terms (pyannote is gated on the Hugging Face hub; Sortformer runs under NVIDIA NeMo); (b) approve the dependency (pyannote.audio or NeMo) and the model weights; (c) decide where the speaker count comes from for AC-4 (the job has no field for it yet) | Terms, tokens, dependencies and licences are the owner's decision (AUTOPILOT §5); the DER baseline needs the human reference set (R-001) | Port, pure assignment and the pipeline wiring are built and tested with a fake; no adapter; AC-4 and AC-5 deferred | D-056 |

## Instructions for the next run
- S20 merged (PR #35). R-006: run promtool locally or accept the CI `alerts` job as the check. Follow-ups in BUILD_LOG S20: per-stage spans, metric call sites, secret encryption before S21.
- PR #34 (S16) reviewed by the run: CI green, no xfail left, 23 evaluation tests pass. Not merged: it depends on partial S12. Decide the partial-dependency rule (D-054).
- R-007 (next run): the autopilot is blocked because every remaining slice depends on a partial one (state.blocked_reason). Decide: may dependents proceed on partial dependencies, or do R-003/R-004/R-005 first?
- R-002 done: S01 pushed and merged. S02 merged 714136b.
- S00 is partial. R-001 stays open: the dev hour must be transcribed by a person from in-house audio placed in `data/` (outside git). The repo has no audio yet.
- Next: S09 (ingest). S00 proceeds on `partial`, so dependents may continue.
- PR #29 (`fix/S11-mypy-numpy`, makes main green) is green on CI but the merge was denied by the permission system on 2026-11-26. Merge it (rebase), then rebase feat/S12-asr-adapters onto main.
- R-003: see the row above; S12 continues with the vLLM path until approved.
<!-- Write instructions here, e.g. "R-001 done: data in data/eval/; finish S00 and revisit D-001". -->
