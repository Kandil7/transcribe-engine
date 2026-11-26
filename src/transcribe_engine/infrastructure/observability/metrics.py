"""Prometheus metrics the design asks for (S20, design: المراقبة). GPU metrics come from the DCGM
exporter in deployment, not from this process.

Names follow `transcribe_<what>_<unit>`. Ratios are computed in PromQL: cache hit ratio is
hits / lookups, suspect ratio is suspect / segments.
"""

from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    "CACHE_HITS",
    "CACHE_LOOKUPS",
    "JOB_FAILURES",
    "JOB_OUTCOMES",
    "LEASE_EXPIRIES",
    "QUEUE_DEPTH_AUDIO_SECONDS",
    "QUEUE_DEPTH_JOBS",
    "QUEUE_OLDEST_JOB_SECONDS",
    "QUEUE_WAIT_SECONDS",
    "SEGMENTS",
    "STAGE_RTF",
    "SUSPECT_SEGMENTS",
]

QUEUE_DEPTH_JOBS = Gauge("transcribe_queue_depth_jobs", "Jobs waiting to be claimed", ["queue"])
QUEUE_DEPTH_AUDIO_SECONDS = Gauge(
    "transcribe_queue_depth_audio_seconds", "Audio seconds waiting to be claimed", ["queue"]
)
QUEUE_OLDEST_JOB_SECONDS = Gauge(
    "transcribe_queue_oldest_job_seconds", "Age of the oldest QUEUED job, per queue", ["queue"]
)
QUEUE_WAIT_SECONDS = Histogram(
    "transcribe_queue_wait_seconds", "Seconds from job creation to its first claim", ["queue"]
)
STAGE_RTF = Histogram(
    "transcribe_stage_rtf",
    "Processing time divided by audio duration, per pipeline stage",
    ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
JOB_FAILURES = Counter("transcribe_job_failures", "Failed jobs by error code", ["error_code"])
JOB_OUTCOMES = Counter("transcribe_job_outcomes", "Terminal job outcomes", ["outcome"])
CACHE_LOOKUPS = Counter("transcribe_cache_lookups", "Result cache lookups")
CACHE_HITS = Counter("transcribe_cache_hits", "Result cache hits")
SEGMENTS = Counter("transcribe_segments", "Transcript segments produced")
SUSPECT_SEGMENTS = Counter("transcribe_suspect_segments", "Segments flagged as suspect")
LEASE_EXPIRIES = Counter("transcribe_lease_expiries", "Leases that expired and were reclaimed")
