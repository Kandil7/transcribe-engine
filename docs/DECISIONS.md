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
