"""Puryfi protocol manifest tests."""

import tomllib
from pathlib import Path

from realtime.protocol import manifest

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_manifest_version_matches_pyproject() -> None:
    """The manifest must not duplicate the project version."""
    with PYPROJECT_PATH.open("rb") as file:
        expected = tomllib.load(file)["project"]["version"]

    assert manifest["version"] == expected
