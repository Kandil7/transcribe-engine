# Experiment 02 — Phrase-loop artifact resolution

Date: 2026-10-30. Follow-up to `wer-spotcheck-01.md`, which hypothesized a
"VAD-chunk/decoder loop" behind near-verbatim repeated passages.

## Method

Scanned all 41 completed transcripts (`transcript_raw`) for repeated
8-word shingles per video, counting occurrences (non-overlapping metric)
instead of pairs:

```
repeat pair math gotcha: every 8-gram repeated n times yields ~8 shifted
shingles x C(n,2) pairs — pair counts inflate quadratically. A "248 pairs"
video actually has a 9x-repeated (4,6,8)-gram of speech filler.
```

## Result: no decoder loops. All repeats are genuine speech.

| Video | distinct repeated 8-grams | max repeats | explanation |
|---|---|---|---|
| `R0UFTKrMnbE` (7084s, 17,285 words) | 2 | 31 | lecturer re-states his series intro promise ("سلسلة استعداد ندعوها إني أعدك بسبع ذاكرات…") at every lesson transition — verified in context |
| `a2bH49afUEI` | 1 | 7 | single rhetorical repeat |
| `oZyeeBFMdD0` | 239 | 4 | low-grade speech filler ("هتخلص دي وبعد كده") repeated ~9x total; 62 segments are 60 unique texts — no segment collapse |
| `LxaKkb-jU98`, `AeVhRpg0OuY`, `ZXWzWWXzPmU`, `j7c3F6D_R1U` | few | 2–3 | hadith/recited passage re-quoted within the same sermon, plus the same canonical passages appearing across episodes of the series (same teacher, sibling videos) |

Distribution across 41 videos: max-repeat histogram
`{2: 12, 3: 2, 4: 1, 7: 1, 31: 1}` — only 5 videos exceed 2 repeats, and
each extreme case is inspectable speech, not model hallucination.

## Conclusion

- **Verdict: artifact rejected.** The pipeline (VAD → ASR → align) shows no
  repetition-collapse pathology on this corpus; `qa=clean` on all 41.
- The cross-video exact matches previously seen in spot-checks are the
  teacher quoting the same hadith in consecutive lessons — an argument for
  later adding per-video uniqueness stats before corpus training, since
  sibling lessons legitimately overlap in quoted material (v2 QA-score
  item in the roadmap).
- No suppression heuristic should be added to the pipeline: it would damage
  legitimately repeated religious formulae.

Work scripts live in the opencode temp dir (`loop_scan.py`, `loop_final.py`),
not committed; the metrics above are the durable record.
