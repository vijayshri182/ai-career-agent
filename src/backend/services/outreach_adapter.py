"""Outreach sending adapters.

Defines the pluggable :class:`OutreachSender` protocol and a safe recording
default. No real network/email interaction happens here; real email/social
providers plug in behind the same protocol and MUST keep every safety gate in
:mod:`backend.services.outreach` (verified destination, approved approval,
suppression, daily cap, idempotent runs, audit).

The default sender only records that the message would be sent: the
``OutreachRun`` row plus audit trail form the durable send record, keeping
development and tests deterministic, network-free and safe. If an external
messaging integration requires credentials/OAuth/human authorization, that
adapter is implemented as code + documented human setup; it never fabricates
credentials.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID

from backend.models.outreach import OutreachChannel


class SendOutcomeKind(str, Enum):
    """How one send attempt completed."""

    SENT = "sent"
    FAILED = "failed"


@dataclass
class OutreachPayload:
    """Non-secret material an adapter needs to perform a send."""

    message_id: UUID
    to_address: str
    subject: str
    body: str
    contact_name: str
    company_name: str
    job_title: str
    channel: OutreachChannel = OutreachChannel.EMAIL


@dataclass
class SendOutcome:
    """Result of a single send attempt (no secrets, no tokens)."""

    kind: SendOutcomeKind
    message: str = ""
    retryable: bool = True
    provider_message_id: str | None = None
    details: dict[str, object] | None = None


class OutreachSender(Protocol):
    async def send(self, payload: OutreachPayload) -> SendOutcome:
        """Perform (or simulate) one send attempt."""


class RecordingSender:
    """Default sender: records a successful send for a permitted message.

    Suitable for development, tests, and as a safe baseline when an external
    provider is not configured. It performs no network or provider automation.
    """

    async def send(self, payload: OutreachPayload) -> SendOutcome:
        return SendOutcome(
            kind=SendOutcomeKind.SENT,
            message="Outreach recorded (no external sender configured)",
            provider_message_id="RECORDED",
            details={
                "message_id": str(payload.message_id),
                "to": payload.to_address,
                "contact": payload.contact_name,
                "company": payload.company_name,
                "job_title": payload.job_title,
                "channel": payload.channel.value,
                "mode": "recording",
            },
        )


def make_sender() -> OutreachSender:
    """Build the default sender (injectable for tests and adapters)."""
    return RecordingSender()
