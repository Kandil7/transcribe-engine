# S04 — Arabic text normalization

| | |
|---|---|
| Phase | 2 |
| Depends on | S01 |
| Branch | `feat/S04-arabic-text-normalization` |
| Design sections | خط الأنابيب › 7. المعالجة اللاحقة للعربية؛ اختيار النماذج والتقييم › المقاييس (نفس الـ Normalizer)؛ نواتج النظام › التمثيل المرجعي |
| ADRs | — (Q1 may produce one) |

## Goal
A single deterministic function that turns display text into search text and returns an offset map
back to the original, used by search, RAG and evaluation alike.

## Interfaces
```python
@dataclass(frozen=True)
class NormalizedText:
    raw: str
    search: str
    offsets: tuple[int, ...]   # offsets[i] = index in `raw` of search[i]

def normalize(raw: str) -> NormalizedText: ...
def map_span(n: NormalizedText, start: int, end: int) -> tuple[int, int]:
    """search-text span → raw-text span (end exclusive)."""
```

## Files
- `src/transcribe_engine/domain/text.py`
- `tests/unit/domain/test_text.py`, `tests/unit/domain/test_text_properties.py`
- `tests/unit/domain/fixtures/normalization_cases.tsv` — raw ⇥ expected search, ≥ 40 rows

## Rules `[D: 7. المعالجة اللاحقة للعربية]`
1. أ إ آ ٱ → ا
2. ى → ي
3. ة → ه
4. Remove tatweel (ـ U+0640) and diacritics (U+064B–U+0652, U+0670).
5. Arabic-Indic digits ٠–٩ and Eastern ۰–۹ → 0–9.
6. Collapse whitespace runs to one space; strip ends.
7. Latin letters lowercased; everything else unchanged.
- `raw` is never modified; `search` is derived `[D: التمثيل المرجعي]`.
- Each rule is a 1:1 character mapping or a deletion, so the offset map is exact.

## Edge cases
- Empty string, whitespace only, Latin only, mixed RTL/LTR, emoji, combining marks after Latin letters.
- A span that starts or ends on a deleted character maps to the nearest kept neighbor.

## Acceptance criteria
- **AC-1** `[D: 7]` — `test_text.py::test_cases_table` (unit): every row of the TSV.
- **AC-2** — `test_text_properties.py::test_idempotent` (Hypothesis): `normalize(n.search).search == n.search`.
- **AC-3** — `test_text_properties.py::test_offsets_point_to_source` (Hypothesis): for every i,
  `fold(raw[offsets[i]]) == search[i]` where `fold` applies rules 1–3, 5, 7 to one char.
- **AC-4** `[D: التمثيل المرجعي]` — `test_text.py::test_map_span_round_trip` (unit): a search hit on
  "الجنيه" in "الجُنَيْه نزل" maps back to the full raw word with diacritics.
- **AC-5** — `test_text_properties.py::test_offsets_monotonic` (Hypothesis).

## Commit plan
1. `docs(S04): add spec`
2. `test(S04): add case table and property tests (xfail)`
3. `feat(S04): add character folding rules`
4. `feat(S04): add whitespace collapse and offset map`
5. `feat(S04): add map_span`

## Open questions
- [ ] Q1 — The design says "التنفيذ عبر CAMeL Tools بدل Regex يدوي", but CLAUDE.md keeps `domain` on the
  standard library. Reading A: a `TextNormalizer` Port with a CAMeL adapter. Reading B: implement these
  character rules in the domain with `str.translate` (no regex) and reserve CAMeL for later morphology.
  Proposed: B — the rules are a fixed character table and the exact offset map is easier in pure code;
  record as ADR and update the design sentence.
- [ ] Q2 — Should Persian/Urdu letters (ک ی) fold to Arabic (ك ي)? Not in the design. Proposed: yes for ی only.
