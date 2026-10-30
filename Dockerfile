# CUDA container for Transcribe Engine (batch CLI; GPU via nvidia-container-toolkit).
#
# Build:  docker build -t transcribe-engine .
# Run:    docker run --gpus all -v %cd%/data:/app/data transcribe-engine \
#             video "https://www.youtube.com/watch?v=VIDEO_ID" --to-parquet data/output/segments.parquet
#
# Targets NVIDIA Turing+ GPUs (sm_75 = RTX 5000 / T4 included). float16
# is the default compute type (Turing has no bf16 units). HF token for the
# gated model goes through HF_TOKEN env, never baked into the image.

FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch first: CUDA wheel pinned to the same major as the base image
RUN pip3 install --break-system-packages \
        torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128

# engine deps (coherex pulls transformers/huggingface_hub itself)
COPY pyproject.toml ./
RUN pip3 install --break-system-packages -e ".[engine]"

# code last: dependency layers stay cached across edits
COPY src/ src/
COPY tests/ tests/

# data/ holds outputs + the optional ffmpeg shim; mount it at run time
VOLUME ["/app/data"]

ENTRYPOINT ["python3", "-m", "src.cli"]
CMD ["--help"]
