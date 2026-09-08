"""Smoke tests that project configuration files are valid YAML."""

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

YAML_FILES = [
    CONFIG_DIR / "app.example.yaml",
    CONFIG_DIR / "settings.example.yaml",
    CONFIG_DIR / "schedules.example.yaml",
]


def pytest_generate_tests(metafunc):
    if "config_file" in metafunc.fixturenames:
        metafunc.parametrize("config_file", YAML_FILES, ids=[p.name for p in YAML_FILES])


def test_yaml_config_loads(config_file: Path) -> None:
    """Each example config must be valid, non-empty YAML."""
    assert config_file.exists(), f"{config_file} does not exist"
    with config_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data, f"{config_file} loaded empty YAML"
