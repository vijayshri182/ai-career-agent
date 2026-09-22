"""Deterministic adapter translating the persisted Gate 4E CP10 artifact into
the CP13 versioned envelope.

Responsibility split (from CP12/CP14):
* Gate 4E owns the persisted evidence (company identity, official source
  evidence, verification, provenance, evidence URLs, Gmail alert metadata).
* ACA owns ingestion/persistence/deduplication/matching/workflow.

This adapter only *copies* producer data across the boundary, adds versioning
metadata, and validates structure. It never:

* fabricates or derives a URL,
* fetches or dereferences any URL (offline JSON-only),
* reinterprets verification status or other evidence,
* calculates match scores or rankings,
* touches the matching engine.

The consumer-side classification (VERIFIED/PARTIAL/quarantine) remains the
CP13 ``Gate4eIngestionService``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from backend.core.exceptions import ValidationError
from backend.schemas.gate4e import Gate4eIngressEnvelope
from backend.schemas.gate4e_cp10 import (
    GATE4E_CP10_PRODUCER_ID,
    GATE4E_CP10_PRODUCER_VERSION,
    GATE4E_CP10_SCHEMA_VERSION,
    GATE4E_CP10_SUPPORTED_ARTIFACTS,
    Gate4eCp10Artifact,
)

_KNOWN_EMPTY_TEXTS = {"", "unknown", "n/a", "na", "null", "none", "-"}


class Gate4eCp10Adapter:
    """Offline translator: persisted CP10 JSON -> CP13 versioned envelope."""

    def load_artifact(self, path: str | Path) -> Gate4eCp10Artifact:
        """Read a persisted CP10 artifact file and validate its structure."""
        artifact_path = Path(path)
        try:
            raw = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"cannot read CP10 artifact {artifact_path}: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"CP10 artifact is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValidationError("CP10 artifact must be a JSON object")
        return self.validate_artifact(payload)

    def validate_artifact(self, payload: dict[str, Any]) -> Gate4eCp10Artifact:
        """Validate an already-loaded artifact dict deterministically."""
        try:
            artifact = Gate4eCp10Artifact.model_validate(payload)
        except PydanticValidationError as exc:
            first = exc.errors()[0]
            raise ValidationError(
                f"CP10 artifact structure invalid at {first.get('loc', [])}: {first['msg']}"
            ) from exc

        if artifact.artifact not in GATE4E_CP10_SUPPORTED_ARTIFACTS:
            raise ValidationError(f"unsupported CP10 artifact: {artifact.artifact!r}")
        if artifact.alerts_evaluated != len(artifact.rows):
            raise ValidationError(
                f"alerts_evaluated={artifact.alerts_evaluated} does not match "
                f"rows count={len(artifact.rows)}"
            )
        return artifact

    def build_envelope(
        self,
        artifact: Gate4eCp10Artifact,
        *,
        generated_at: str | None = None,
    ) -> Gate4eIngressEnvelope:
        """Translate a validated CP10 artifact into the CP13 versioned envelope.

        Producer ``rows`` are copied verbatim; a runtime ISO-8601 UTC
        ``generated_at`` (handoff time) is added unless supplied. Handoff
        metadata never alters record content, and the CP13 ingestion identity
        excludes ``generated_at`` so replays stay idempotent regardless.
        """
        return Gate4eIngressEnvelope(
            schema_version=GATE4E_CP10_SCHEMA_VERSION,
            producer_id=GATE4E_CP10_PRODUCER_ID,
            producer_version=GATE4E_CP10_PRODUCER_VERSION,
            generated_at=generated_at or datetime.now(UTC).isoformat(),
            labels=list(artifact.labels),
            alerts_evaluated=artifact.alerts_evaluated,
            rows=[dict(row) for row in artifact.rows],
        )

    def load_envelope(
        self,
        path: str | Path,
        *,
        generated_at: str | None = None,
    ) -> Gate4eIngressEnvelope:
        """Load the persisted artifact and translate it to a CP13 envelope."""
        return self.build_envelope(self.load_artifact(path), generated_at=generated_at)

    # ------------------------------------------------------------------ #
    # Deterministic reporting helpers (no DB, no network)
    # ------------------------------------------------------------------ #

    def summarize_artifact(self, artifact: Gate4eCp10Artifact) -> dict[str, Any]:
        """Deterministic structural summary of a validated artifact."""
        verification_counts: dict[str, int] = {}
        posting_keys: set[str] = set()
        alert_ids: set[str] = set()
        for row in artifact.rows:
            status = row.get("verification_status")
            verification_counts[str(status)] = verification_counts.get(str(status), 0) + 1
            key = self.posting_identity_hint(row)
            if key is not None:
                posting_keys.add(key)
            gmail_id = row.get("gmail_message_id")
            if isinstance(gmail_id, str) and gmail_id:
                alert_ids.add(gmail_id)
        return {
            "artifact": artifact.artifact,
            "alerts_evaluated": artifact.alerts_evaluated,
            "rows_count": len(artifact.rows),
            "alert_identity_count": len(alert_ids),
            "posting_identity_hint_count": len(posting_keys),
            "verification_counts": verification_counts,
        }

    def posting_identity_hint(self, row: dict[str, Any]) -> str | None:
        """Stable identity-B hint: normalized company_name|job_title key.

        Matches the CP13 posting-key basis (normalized company + title) and is
        used only for reporting; ACA dedup remains authoritative for identity C.
        """
        company = self._normalize_text(row.get("company_name")).lower()
        title = self._normalize_text(row.get("job_title")).lower()
        if not company or not title:
            return None
        return hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[0:32]

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        stripped = " ".join(value.split())
        if stripped.lower() in _KNOWN_EMPTY_TEXTS:
            return ""
        return stripped
