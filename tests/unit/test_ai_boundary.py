"""Tests enforcing the deterministic-only runtime boundary.

The product is explicitly deterministic: matching, scoring, normalization,
quality checks and document generation are rule-based and never invoke an
external model. This suite guards the declared runtime against reintroducing
LLM/vector SDKs.
"""

from pathlib import Path
from tomllib import load

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Model-serving / vector SDKs are never declared or imported.
FORBIDDEN_DEPENDENCIES = {
    "langchain",
    "langchain-openai",
    "langgraph",
    "pgvector",
    "openai",
    "anthropic",
    "cohere",
    "transformers",
    "sentence-transformers",
    "torch",
}

# Import lines that must never reach the runtime.
FORBIDDEN_IMPORT_PREFIXES = (
    "import openai",
    "from openai",
    "import anthropic",
    "from anthropic",
    "import langchain",
    "from langchain",
    "import langgraph",
    "from langgraph",
    "from pgvector",
    "import torch",
    "from torch",
    "from transformers",
    "import tiktoken",
)


def test_runtime_dependencies_contain_no_ai_sdks() -> None:
    with PYPROJECT.open("rb") as fh:
        data = load(fh)
    deps = data["project"]["dependencies"]
    declared = {dep.split(">=")[0].split("<")[0].split("[")[0].strip() for dep in deps}
    assert not (declared & FORBIDDEN_DEPENDENCIES)


@pytest.mark.parametrize("prefix", FORBIDDEN_IMPORT_PREFIXES)
def test_source_contains_no_ai_imports(prefix: str) -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(prefix):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
    assert not offenders, f"forbidden import '{prefix}' found in {offenders}"
