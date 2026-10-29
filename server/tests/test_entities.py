"""Tests for the PuryFi object label enum (SDK review 6.1)."""

from domain.entities import PuryfiObjectLabel


def test_silhouette_matches_sdk_label() -> None:
    assert PuryfiObjectLabel.Silhouette == 26


def test_get_name_returns_silhouette() -> None:
    assert PuryfiObjectLabel.get_name(26) == "Silhouette"


def test_get_name_returns_none_for_unknown_label() -> None:
    assert PuryfiObjectLabel.get_name(27) is None
