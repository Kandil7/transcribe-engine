# Local environment

Filled by the autopilot during bootstrap from read-only commands. Re-run discovery if hardware changes.

| Item | Value | Command |
|---|---|---|
| OS / version | | `uname -a`, `sw_vers` / `/etc/os-release` |
| CPU cores | | `nproc` / `sysctl -n hw.ncpu` |
| RAM | | `free -g` / `sysctl -n hw.memsize` |
| Free disk | | `df -h .` |
| GPU / VRAM | | `nvidia-smi --query-gpu=name,memory.total --format=csv` / Apple Silicon `uname -m` |
| Docker / Compose | | `docker version`, `docker compose version` |
| uv / Python | | `uv --version`, `python3 --version` |
| FFmpeg | | `ffmpeg -version` |

## Chosen local runtime profile
Profile: — (see D-001)
ASR engine locally: —
How to start: `make up && make dev`
How to demo: `make demo FILE=path/to/audio.mp3` → `out/<job>.json|.srt|.vtt`

## Known local limitations
-
