"""Project structure and documentation standards."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _is_gitignored(name: str) -> bool:
    try:
        return subprocess.run(
            ["git", "check-ignore", "-q", name],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def test_no_env_file_committed() -> None:
    """Real environment files must never be committed."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        assert _is_gitignored(".env"), ".env must be gitignored so it is never committed"


def test_no_raw_placeholder_tokens() -> None:
    """Documentation and config must not contain raw {{PLACEHOLDER}} tokens."""
    exclude_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next"}
    bad_files = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in exclude_dirs for part in path.parts):
            continue
        if path.suffix not in {".md", ".yaml", ".yml", ".json", ".toml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "{{" in text and "}}" in text:
            bad_files.append(path.relative_to(PROJECT_ROOT))
    assert not bad_files, f"Raw placeholder tokens found in: {bad_files}"


def test_required_root_docs_exist() -> None:
    """Core documentation files must be present."""
    required = [
        "README.md",
        "PROJECT_PLAN.md",
        "ARCHITECTURE.md",
        "AGENT_ARCHITECTURE.md",
        "DATA_MODEL.md",
        "SECURITY.md",
        "ROADMAP.md",
        "DEVELOPMENT_GUIDELINES.md",
        "CONTRIBUTING.md",
    ]
    for name in required:
        assert (PROJECT_ROOT / name).exists(), f"Missing required file: {name}"
