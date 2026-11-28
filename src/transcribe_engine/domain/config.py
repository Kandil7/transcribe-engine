"""Processing configuration and its canonical serialization (S03).

Field order in the dataclass never changes the serialized form: canonical JSON sorts keys
at every level.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

__all__ = ["PipelineConfig"]

ParamValue = str | int | float | bool


def _check_flat(name: str, params: Mapping[str, object]) -> Mapping[str, ParamValue]:
    checked: dict[str, ParamValue] = {}
    for key, value in params.items():
        is_str_key = isinstance(key, str)
        if not is_str_key:
            raise ValueError(f"{name} keys must be strings")
        is_scalar = isinstance(value, str | bool | int | float)
        if not is_scalar:
            raise ValueError(f"{name} must be a flat mapping of scalar values")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name}.{key} must be finite")
        checked[key] = cast(ParamValue, value)  # narrowed by is_scalar above
    return MappingProxyType(checked)  # read-only: the key must not change after construction


@dataclass(frozen=True)
class PipelineConfig:
    engine: str
    model_revision: str
    language: str  # explicit language code, never "auto"
    decoding_params: Mapping[str, ParamValue]
    vad_params: Mapping[str, ParamValue]
    diarization_enabled: bool
    pipeline_version: str
    speakers: int | None = (
        None  # requested speaker count, 1 to 10; part of the hash only when set (D-083)
    )

    def __post_init__(self) -> None:
        if self.language.strip().lower() in ("", "auto"):
            raise ValueError("language must be an explicit language code")
        object.__setattr__(
            self, "decoding_params", _check_flat("decoding_params", self.decoding_params)
        )
        object.__setattr__(self, "vad_params", _check_flat("vad_params", self.vad_params))
        if self.speakers is not None and not 1 <= self.speakers <= 10:
            raise ValueError("speakers must be between 1 and 10")

    def canonical_json(self) -> str:
        payload = {
            "engine": self.engine,
            "model_revision": self.model_revision,
            "language": self.language,
            "decoding_params": dict(self.decoding_params),
            "vad_params": dict(self.vad_params),
            "diarization_enabled": self.diarization_enabled,
            "pipeline_version": self.pipeline_version,
        }
        if (
            self.speakers is not None
        ):  # left out when unset, so existing hashes do not change (D-083)
            payload["speakers"] = self.speakers
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )

    # Equality is the canonical form (D-016): a read-only mapping compares by identity otherwise.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PipelineConfig):
            return NotImplemented
        return self.canonical_json() == other.canonical_json()

    def __hash__(self) -> int:
        return hash(self.canonical_json())

    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
