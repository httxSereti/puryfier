"""Application version resolved from a single source of truth."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path

DISTRIBUTION_NAME = "puryfi-chaster-linker-ws"
PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _read_pyproject_version() -> str | None:
    """Return the version declared in ``pyproject.toml`` when available."""
    try:
        with PYPROJECT_PATH.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    project = data.get("project")
    if not isinstance(project, dict):
        return None

    value = project.get("version")
    return value if isinstance(value, str) and value else None


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the application version.

    ``pyproject.toml`` is the source of truth in the repository and in the
    Docker image. Installed distributions without that file fall back to the
    package metadata generated from it.
    """
    project_version = _read_pyproject_version()
    if project_version is not None:
        return project_version

    try:
        return distribution_version(DISTRIBUTION_NAME)
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "Cannot determine the application version: pyproject.toml is "
            f"missing and the {DISTRIBUTION_NAME!r} distribution is not installed"
        ) from exc


__version__ = get_version()
