# Transcribe Engine

Arabic batch speech-to-text platform: async jobs, swappable ASR engines, word-level timestamps,
subtitles in several formats, and RAG-ready outputs.

| Where | What |
|---|---|
| `docs/design.md` | Design document (Arabic) — the source of truth |
| `docs/adr/` | Architecture decisions |
| `docs/WORKFLOW.ar.md` | How to build this with Claude Code: specs, branches, commits (Arabic) |
| `specs/` | One spec per vertical slice, S00–S22, with dependency order |
| `CONTRIBUTING.md` | Branch, commit and PR rules |
| `CLAUDE.md` | Rules Claude Code loads every session |
| `.claude/` | Hooks, skills, subagents |

## Quick start
```bash
make setup        # uv sync + git hooks
make up           # Postgres (pgvector) + MinIO
make check        # the gate every commit must pass
```
