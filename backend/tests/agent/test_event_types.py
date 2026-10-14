from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.event_types import load_event_types


def test_default_file_has_the_three_types() -> None:
    types = load_event_types()

    assert [t.key for t in types] == ["missing_ppe", "unsafe_proximity", "fallen_object_or_spill"]
    assert types[1].default_severity == "high"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "types.yaml"
    path.write_text(text)
    return path


def test_duplicate_keys_rejected(tmp_path: Path) -> None:
    entry = "- {key: spill, label: Spill, description: A spill., default_severity: low}\n"
    with pytest.raises(ValueError, match="Duplicate"):
        load_event_types(_write(tmp_path, entry * 2))


def test_invalid_severity_rejected(tmp_path: Path) -> None:
    entry = "- {key: spill, label: Spill, description: A spill., default_severity: critical}\n"
    with pytest.raises(ValidationError):
        load_event_types(_write(tmp_path, entry))
