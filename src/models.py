"""Model IDs — the single source of truth.

Every consumer (engine config, CLI defaults, prefetch loaders, feature
modules) references these constants instead of repeating repo-id
literals. Add a model here once and the whole pipeline agrees.
"""

# ASR: Cohere Arabic (gated on HF; the only gated model in the project)
AR_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"

# Forced alignment: wav2vec2 Arabic (matches coherex DEFAULT_ALIGN_MODELS_HF["ar"])
ALIGN_MODEL_AR = "jonatasgrosman/wav2vec2-large-xlsr-53-arabic"

# Speaker diarization: sole backend since ADR 18 (pyannote removed)
DIARIZE_MODEL = "nvidia/Nemotron-3-Diarization"

# Audio language ID (CC-BY-NC model, see ADR 14)
LID_MODEL = "facebook/mms-lid-1024"

# Written-dialect classification (see ADR 16)
DIALECT_MODEL = "IbrahimAmin/marbertv2-arabic-written-dialect-classifier"
