"""Audio profile and routing policy (S13, design §1.5). Pure domain logic, stdlib only.

`plan_processing` maps a chunk's measured profile to the steps it needs. The thresholds live in
`RoutingPolicy`; they are initial values and change only with a policy version, which bumps
`pipeline_version` (S03 Q1). Any change to the rules also bumps the version.

Rules:
- A step is applied only when a condition needs it. Clean audio gets an empty plan (AC-2).
- `feed_asr` is "enhanced" only when the ASR receives transformed audio (loudness or vocals).
  Denoising is for VAD and diarization only, so ASR keeps the original (design table).
- `skip_asr` (no speech) empties the steps: no GPU work is planned for a chunk that will not be
  transcribed.

Singing (AudioSet class) is not in AudioProfile yet; it is a follow-up (D-044).
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

__all__ = ["AudioProfile", "ProcessingPlan", "RoutingPolicy", "Step", "plan_processing"]


class Step(StrEnum):
    # Order is the order the steps run in.
    LOUDNORM = "Loudnorm"
    DENOISE = "Denoise"
    SEPARATE_VOCALS = "SeparateVocals"
    SPLIT_CHANNELS = "SplitChannels"


@dataclass(frozen=True)
class AudioProfile:
    snr_db: float
    c50_db: float
    music_ratio: float
    speech_ratio: float
    overlap_ratio: float
    clipping_ratio: float
    loudness_lufs: float
    source_sample_rate: int
    channels: int
    quality_mos: float


@dataclass(frozen=True)
class RoutingPolicy:
    version: str = "1"
    clean_snr_db: float = 15.0  # above: clean
    heavy_noise_snr_db: float = 5.0  # below: heavy noise
    music_ratio: float = 0.30
    no_speech_ratio: float = 0.02
    reverb_c50_db: float = 10.0  # below: reverberant (proposed, tuned in S16)
    telephony_sample_rate: int = 8000
    quiet_lufs: float = -35.0  # below: quiet, apply loudness normalization
    target_lufs: float = -23.0
    clipping_ratio: float = 0.01
    overlap_ratio: float = 0.15  # proposed, tuned in S16
    vad_default: float = 0.5
    vad_strict: float = 0.7


@dataclass(frozen=True)
class ProcessingPlan:
    steps: tuple[Step, ...]
    feed_asr: Literal["original", "enhanced"]
    vad_threshold: float
    flags: frozenset[str] = field(default_factory=frozenset)
    skip_asr: bool = False


def plan_processing(profile: AudioProfile, policy: RoutingPolicy) -> ProcessingPlan:
    steps, flags, vad = _noise_and_level(profile, policy)
    steps |= _music_and_channels(profile, policy)
    flags |= _acoustic_flags(profile, policy)

    skip_asr = profile.speech_ratio < policy.no_speech_ratio
    if skip_asr:
        flags.add("no_speech")
        if profile.music_ratio > policy.music_ratio:
            flags.add("music")
        steps.clear()

    ordered = tuple(step for step in Step if step in steps)
    feed_asr: Literal["original", "enhanced"] = (
        "enhanced" if Step.LOUDNORM in ordered or Step.SEPARATE_VOCALS in ordered else "original"
    )
    return ProcessingPlan(
        steps=ordered,
        feed_asr=feed_asr,
        vad_threshold=vad,
        flags=frozenset(flags),
        skip_asr=skip_asr,
    )


def _noise_and_level(
    profile: AudioProfile, policy: RoutingPolicy
) -> tuple[set[Step], set[str], float]:
    steps: set[Step] = set()
    flags: set[str] = set()
    vad = policy.vad_default
    if profile.snr_db < policy.heavy_noise_snr_db:
        flags.add("low_snr")
        vad = policy.vad_strict
    elif profile.snr_db <= policy.clean_snr_db:
        steps.add(Step.DENOISE)  # for VAD and diarization only; ASR keeps the original
    if profile.loudness_lufs < policy.quiet_lufs:
        steps.add(Step.LOUDNORM)
    return steps, flags, vad


def _music_and_channels(profile: AudioProfile, policy: RoutingPolicy) -> set[Step]:
    steps: set[Step] = set()
    if profile.music_ratio > policy.music_ratio:
        steps.add(Step.SEPARATE_VOCALS)
    if profile.channels == 2:
        steps.add(Step.SPLIT_CHANNELS)
    return steps


def _acoustic_flags(profile: AudioProfile, policy: RoutingPolicy) -> set[str]:
    flags: set[str] = set()
    if profile.c50_db < policy.reverb_c50_db:
        flags.add("reverb")
    if profile.source_sample_rate == policy.telephony_sample_rate:
        flags.add("telephony")
    if profile.overlap_ratio > policy.overlap_ratio:
        flags.add("overlap")
    if profile.clipping_ratio > policy.clipping_ratio:
        flags.add("clipping")
    return flags
