---
name: write-adr
description: Record an architecture decision that the spec or design doc does not already cover.
argument-hint: <short title>
---
1. Next number: `ls docs/adr | sort | tail -1`. File: `docs/adr/NNNN-<kebab-title>.md`.
2. Template (keep under 40 lines):
   ```markdown
   # NNNN. <Title>
   Status: Accepted | Proposed | Superseded by NNNN
   Date: YYYY-MM-DD   Slice: SXX

   ## Context
   <the force or problem, 3–5 lines, with numbers if any>
   ## Decision
   <what we do, in one paragraph>
   ## Alternatives considered
   - <option>: <why not>
   ## Consequences
   - <what gets easier / harder; what we must now monitor>
   ```
3. If the decision changes the design doc, update that section in the same commit and link the ADR.
4. Commit: `docs(adr): NNNN <title>`.
