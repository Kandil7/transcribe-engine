"""Outbox events (S20). The names are part of the public webhook contract; a change is a breaking
change for clients. Pure domain logic."""

from enum import StrEnum

__all__ = ["OutboxEvent", "event_for_state"]


class OutboxEvent(StrEnum):
    TRANSCRIPT_COMPLETED = "transcript.completed"
    TRANSCRIPT_FAILED = "transcript.failed"
    INDEX_COMPLETED = "index.completed"
    ENRICHMENT_COMPLETED = "enrichment.completed"


# Terminal job states that produce an event, by state value. CANCELLED produces none (S20 spec).
_EVENT_FOR_STATE: dict[str, OutboxEvent] = {
    "COMPLETED": OutboxEvent.TRANSCRIPT_COMPLETED,
    "FAILED": OutboxEvent.TRANSCRIPT_FAILED,
}


def event_for_state(state: str) -> OutboxEvent | None:
    """The outbox event a job state emits, or None if the state emits nothing."""
    return _EVENT_FOR_STATE.get(state)
