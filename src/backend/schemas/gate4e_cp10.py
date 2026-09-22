"""Gate 4E CP10 persisted-artifact schema (adapter input).

Models the CP10 official-postings artifact as produced and persisted by Gate 4E.
The producer envelope is unversioned today (CP12 contract-mapping note:
``existing_versioning: None in the artifact envelope today``), so the CP14
adapter validates the persisted shape here and wraps it in the versioned CP13
envelope at translation time.

This module performs no verification, no reinterpretation, and no network I/O:
the ``rows`` are preserved verbatim as opaque data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

GATE4E_CP10_ARTIFACT_NAME = "gate4e-cp10-official-postings"
GATE4E_CP10_SUPPORTED_ARTIFACTS = frozenset({GATE4E_CP10_ARTIFACT_NAME})

# Version added onto the unversioned CP10 artifact by the CP14 adapter.
GATE4E_CP10_SCHEMA_VERSION = 1
GATE4E_CP10_PRODUCER_ID = "gate4e"
GATE4E_CP10_PRODUCER_VERSION = "cp10-official-postings"


class Gate4eCp10Artifact(BaseModel):
    """Validated top-level structure of the persisted CP10 artifact."""

    artifact: str
    labels: list[str] = []
    alerts_evaluated: int
    rows: list[dict[str, Any]]
