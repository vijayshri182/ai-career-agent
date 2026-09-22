"""CP18 recruiter-signal quality and audit contract.

Deterministic, stateless quality evaluation of one persisted
``RecruiterSignal``. The evaluation verifies evidence completeness and
field-level provenance integrity, coherence with the signal type, and that the
signal is in a safe lifecycle state -- it never ranks, scores, predicts,
mutates the signal, nor contacts anyone. Identical persisted inputs produce a
byte-identical report.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RECRUITER_SIGNAL_QUALITY_VERSION = "cp18.v1"


class SignalQualitySeverity(str, Enum):
    """Outcome of one deterministic quality check."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class SignalQualityCheck(BaseModel):
    """One named, deterministic quality check and its result."""

    model_config = ConfigDict(extra="forbid")

    check: str
    severity: SignalQualitySeverity
    detail: str


class RecruiterSignalQualityReport(BaseModel):
    """Deterministic quality report for one signal."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    signal_id: UUID
    quality_version: str = RECRUITER_SIGNAL_QUALITY_VERSION
    # Deterministic evaluation id (no timestamps), for audit correlation.
    evaluation_id: str
    passed: bool
    checks: list[SignalQualityCheck] = []
    failed_checks: list[str] = []
    evaluated_at: datetime | None = None

    def model_dump_deterministic(self) -> dict[str, Any]:
        """Canonical dump for byte-identical evaluation artifacts.

        ``evaluated_at`` is intentionally excluded so identical persisted inputs
        yield identical output across runs.
        """
        data = self.model_dump(mode="json")
        data.pop("evaluated_at", None)
        data["checks"] = sorted(data["checks"], key=lambda c: c["check"])
        data["failed_checks"] = sorted(data["failed_checks"])
        return data
