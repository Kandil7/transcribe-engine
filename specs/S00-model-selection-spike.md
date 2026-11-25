# S00 — Model selection spike

| | |
|---|---|
| Phase | 0 |
| Depends on | — (runs in parallel with S01–S10) |
| Branch | `spike/S00-model-selection` |
| Design sections | اختيار النماذج والتقييم › المرشحون، مجموعة التقييم، المقاييس؛ خارطة الطريق › المراحل (0)؛ حدود التشغيل المبدئية |
| ADRs | produces ADR-0007 (default ASR engine) |

## Goal
A written, numbers-backed decision on the default ASR engine, its runtime, VRAM, RTF, and whether
forced alignment is mandatory, measured on our own Egyptian audio. No product code.

## Scope
- In: annotation guidelines, ≥ 1 h manually transcribed Egyptian audio (dev split), notebook runs of
  Audar-ASR-V1-Turbo, Cohere Transcribe Arabic (07-2026), Whisper large-v3; vLLM serving check for
  Audar (Qwen3-ASR format) and Cohere; RTF/VRAM on the target GPU (L4 initially).
- Out (→ S16): the reusable evaluation harness, robustness matrix, CI gate.
- Out: Falcon-ASR until weights and a commercial license are published `[D: المرشحون]`.

## Deliverables
- `evaluation/guidelines.ar.md` — transcription rules: dialect spelling (عايز/عاوز), digits vs words,
  English words script, fillers, repetitions, overlap markup, unintelligible markup.
- `evaluation/spike/manifest.jsonl` — `{audio, offset_ms, duration_ms, text, speaker, conditions}`; audio
  itself stays outside git (`data/`).
- `evaluation/spike/run.ipynb` — reproducible runs; seeds and decoding params printed.
- `evaluation/spike/REPORT.md` — results table + decision.
- `docs/adr/0007-default-asr-engine.md`.

## Rules
- Same normalizer for reference and hypothesis before WER/CER `[D: المقاييس]`. Until S04 exists, use a
  copy of the rules in "7. المعالجة اللاحقة للعربية" and note it in the report.
- Decoding: `temperature=0`, explicit `language="ar"` `[D: 3. الـ ASR]`.
- BF16 weights; no GGUF/Q4 for the production candidate `[D: تشغيل الـ GPU Worker]`.
- Report published leaderboard numbers only as context, never as the decision basis `[D: المرشحون]`.

## Acceptance criteria
- **AC-1** `[D: مجموعة التقييم]` — guidelines file exists and covers every item listed in Deliverables.
- **AC-2** `[D: مجموعة التقييم]` — ≥ 60 min dev audio transcribed per guidelines, covering ≥ 5 speakers,
  clean + noisy + code-switch + one silent/music clip; manifest validates (script prints counts).
- **AC-3** `[D: المقاييس]` — REPORT table per model: CER, WER, Hallucination rate (as defined in the
  design doc), RTF p50/p95, peak VRAM, runtime used.
- **AC-4** `[D: Adapters المخططة]` — REPORT states whether Audar runs on vLLM, with the exact command
  and version, or the failure and the fallback runtime.
- **AC-5** `[D: المراحل 0]` — ADR-0007 records: default engine, runtime, VRAM, RTF, alignment mandatory
  yes/no, and the trigger to revisit (e.g. Falcon-ASR weights released).

## Commit plan
1. `docs(S00): add spec`
2. `docs(S00): add annotation guidelines`
3. `spike(S00): add manifest validator and dev manifest`
4. `spike(S00): run candidates, record raw results`
5. `docs(S00): add report`
6. `docs(adr): 0007 default ASR engine`

## Open questions
- [ ] Q1 — Who transcribes the reference hour, and is the audio ours or consented? Proposed: in-house
  recordings only `[D: الخصوصية ودورة حياة البيانات]`.
- [ ] Q2 — Target GPU for the decision: L4 (design default) or what we will actually rent?
