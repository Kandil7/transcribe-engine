# Local environment

Filled by the autopilot during bootstrap from read-only commands. Re-run discovery if hardware changes.

| Item | Value | Command |
|---|---|---|
| OS / version | Windows 11 Pro 10.0.26200 (Git Bash MSYS, MINGW64) | `uname -a`, `systeminfo` |
| CPU cores | 12 | `nproc` |
| RAM | 32 GB total (~10.7 GB free at bootstrap) | `systeminfo` |
| Free disk | 115 GB free on D: (82% used) | `df -h .` |
| GPU / VRAM | NVIDIA Quadro RTX 5000, 16384 MiB, driver 580.92 (Turing, no BF16) | `nvidia-smi` |
| Docker / Compose | Docker Engine 29.9.1 (Desktop, linux), Compose v5.6.0 | `docker version`, `docker compose version` |
| uv / Python | uv 0.12.13; Python 3.12.10 in `.venv` | `uv --version` |
| FFmpeg | 9.0.1 full build (gyan.dev) | `ffmpeg -version` |
| GitHub CLI | 2.97.0, logged in | `gh auth status` |

## Chosen local runtime profile
Profile: `local-gpu` (faster-whisper on GPU, FP16) — see D-001
ASR engine locally: faster-whisper (CTranslate2), FP16, Quadro RTX 5000 (to be wired in S12)
Object storage locally: MinIO (Chainguard image) — see D-002
How to start: `make up && make dev`
How to demo: `make demo FILE=path/to/audio.mp3` → `out/<job>.json|.srt|.vtt`

## Known local limitations
- Docker Desktop can't use the GPU for the vLLM BF16 path (Turing has no BF16); local ASR is FP16 instead.
- Pulls from `minio/minio` and `quay.io/minio/minio` are refused on this machine (D-002).
- The `nul` file at repo root is a stray HTML download (gitignored); not part of the build.
