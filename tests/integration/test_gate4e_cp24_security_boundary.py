"""CP24 Gate 4E security-boundary (AST) tests for the signal pipeline.

Verifies, by static analysis, that the CP18/CP19/CP20 pipeline stays inside its
hard boundaries: no network, no outbound outreach, no message/run
construction, and no fabricated data. Only the CP20 preparation service may
touch the grounded writing infra, and even it only ever uses the outreach
``OutreachChannel`` enum -- never the sending service or adapter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_NETWORK_MODULES = {
    "httpx",
    "requests",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "socket",
    "ssl",
    "playwright",
    "selenium",
    "aiohttp",
    "asyncio",
}

_SENDER_MODULES = {
    "backend.services.outreach",
    "backend.services.outreach_adapter",
    "backend.services.service_smtp",
}

_QUALITY_APPROVAL_SOURCES = [
    "src/backend/services/recruiter_signal_quality.py",
    "src/backend/schemas/recruiter_signal_quality.py",
    "src/backend/services/recruiter_signal_approval.py",
]

_PREP_SOURCES = [
    "src/backend/services/recruiter_signal_outreach_prep.py",
    "src/backend/schemas/recruiter_signal_outreach_prep.py",
]

_ALL_SOURCES = _QUALITY_APPROVAL_SOURCES + _PREP_SOURCES


def _imports(relative: str) -> list[str]:
    source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
    tree = __import__("ast").parse(source)
    imported: list[str] = []
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, __import__("ast").ImportFrom) and node.module:
            imported.append(node.module)
    return imported


def _calls(relative: str) -> set[str]:
    source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
    tree = __import__("ast").parse(source)
    names: set[str] = {
        node.func.id
        for node in __import__("ast").walk(tree)
        if isinstance(node, __import__("ast").Call) and isinstance(node.func, __import__("ast").Name)
    }
    names |= {
        node.func.attr
        for node in __import__("ast").walk(tree)
        if isinstance(node, __import__("ast").Call)
        and isinstance(node.func, __import__("ast").Attribute)
    }
    return names


@pytest.mark.parametrize("relative", _ALL_SOURCES)
def test_cp24_sources_never_import_network_or_sender_modules(relative):
    imported = set(_imports(relative))
    top_level = {name.split(".")[0] for name in imported}
    assert not (_NETWORK_MODULES & top_level), f"{relative} imports network modules"
    assert not (_SENDER_MODULES & imported), f"{relative} imports a sender module"


@pytest.mark.parametrize("relative", _QUALITY_APPROVAL_SOURCES)
def test_cp24_quality_and_approval_never_touch_outreach_drafting(relative):
    imported = set(_imports(relative))
    assert "backend.services.outreach_writer" not in imported
    assert "backend.models.outreach" not in imported
    assert "backend.services.recruiter_signal_outreach_prep" not in imported


@pytest.mark.parametrize("relative", _PREP_SOURCES)
def test_cp24_prep_only_reaches_outreach_channel_enum(relative):
    imported = set(_imports(relative))
    assert "backend.services.outreach" not in imported, "prep must not import the sender service"
    assert "backend.services.outreach_adapter" not in imported
    if relative.endswith("recruiter_signal_outreach_prep.py"):
        assert "from backend.models.outreach import OutreachChannel" in (
            _PROJECT_ROOT / relative
        ).read_text(encoding="utf-8")
    assert "OutreachMessage(" not in (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
    assert "OutreachRun(" not in (_PROJECT_ROOT / relative).read_text(encoding="utf-8")


def test_cp24_domain_code_is_offline_by_construction():
    outbound = {"send", "send_email", "send_outreach", "start_browser", "crawl", "fetch"}
    for relative in _ALL_SOURCES:
        source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert not (outbound & _calls(relative)), f"{relative} contains outbound calls"
        assert "OutreachMessage(" not in source
        assert "OutreachRun(" not in source


def test_cp24_pipeline_never_auto_approves_or_scores():
    markers = {
        "recruiter_signal_quality.py": ["ranking", "scoring", "prediction"],
        "recruiter_signal_approval.py": [
            "record_decision(",
            "auto_approve",
        ],
        "recruiter_signal_outreach_prep.py": ["auto_authorize", "auto_send"],
    }
    for filename, needles in markers.items():
        relative = f"src/backend/services/{filename}"
        source = (_PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in source, f"{relative} must not contain {needle!r}"


def test_cp24_versioned_contracts_are_exact():
    import importlib

    cases = {
        "recruiter_signal_quality": {
            "class_name": "RecruiterSignalQualityService",
            "version": "cp18.v1",
            "constant": "RECRUITER_SIGNAL_QUALITY_VERSION",
        },
        "recruiter_signal_outreach_prep": {
            "class_name": "RecruiterSignalOutreachPrepService",
            "version": "cp20.v1",
            "constant": "RECRUITER_SIGNAL_OUTREACH_PREP_VERSION",
        },
    }
    for module_name, meta in cases.items():
        service = importlib.import_module(f"backend.services.{module_name}")
        schema = importlib.import_module(f"backend.schemas.{module_name}")
        assert getattr(schema, meta["constant"]) == meta["version"]
        assert getattr(service, meta["constant"]) == meta["version"]
        assert getattr(service, meta["class_name"]) is not None


def test_cp24_prep_service_requires_approved_review_gate():
    source = (
        _PROJECT_ROOT / "src/backend/services/recruiter_signal_outreach_prep.py"
    ).read_text(encoding="utf-8")
    assert "require_approved_review" in source
    assert "signal.status is not RecruiterSignalStatus.APPROVED" in source
