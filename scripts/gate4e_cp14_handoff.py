"""CP14 Gate 4E -> ACA handoff runner (offline, deterministic).

Loads the persisted Gate 4E CP10 artifact, translates it into the CP13 versioned
envelope, prints a structural summary, and can dump the versioned envelope for
audit. No network, no database, no matching: this validates the handoff shape
only. Full ingestion/persistence is exercised by the CP14 test suite.

Usage:
    python scripts/gate4e_cp14_handoff.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from backend.services.gate4e_cp10_adapter import Gate4eCp10Adapter  # noqa: E402

_DEFAULT_INPUT = _REPO_ROOT / "tests" / "fixtures" / "gate4e_cp10_official_postings.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing")
    parser.add_argument(
        "--generated-at",
        default=datetime.now(UTC).isoformat(),
        help="handoff timestamp (defaults to runtime UTC; not part of ingestion identity)",
    )
    args = parser.parse_args()

    adapter = Gate4eCp10Adapter()
    try:
        artifact = adapter.load_artifact(args.input)
        envelope = adapter.build_envelope(artifact, generated_at=args.generated_at)
    except Exception as exc:  # adapter ValidationError or I/O
        print(f"handoff rejected: {exc}", file=sys.stderr)
        return 2

    summary = adapter.summarize_artifact(artifact)
    report = {
        "status": "handoff_valid",
        "envelope": {
            "schema_version": envelope.schema_version,
            "producer_id": envelope.producer_id,
            "producer_version": envelope.producer_version,
            "generated_at": envelope.generated_at,
            "alerts_evaluated": envelope.alerts_evaluated,
        },
        "summary": summary,
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if not args.dry_run and args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(envelope.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"envelope written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
