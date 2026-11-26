"""Outbox events (S20). The names are part of the public webhook contract; a change is a breaking
change for clients. Pure domain logic."""

from enum import StrEnum

__all__ = ["OutboxEvent"]


class OutboxEvent(StrEnum):
    TRANSCRIPT_COMPLETED = "transcript.completed"
    TRANSCRIPT_FAILED = "transcript.failed"
    INDEX_COMPLETED = "index.completed"
    ENRICHMENT_COMPLETED = "enrichment.completed"
