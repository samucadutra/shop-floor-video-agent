"""Loads the configurable event types (docs/spec.md S6.1)."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, TypeAdapter

from agent.schemas import Severity

DEFAULT_FILE = Path(__file__).parent / "event_types.yaml"


class EventType(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=50)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    default_severity: Severity


def load_event_types(path: Path | str = DEFAULT_FILE) -> list[EventType]:
    """Read and validate the YAML list. Raises ValueError on invalid entries or duplicate keys."""
    data = yaml.safe_load(Path(path).read_text())
    event_types = TypeAdapter(list[EventType]).validate_python(data)
    if not event_types:
        raise ValueError("At least one event type is required.")
    keys = [t.key for t in event_types]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"Duplicate event type keys: {', '.join(duplicates)}")
    return event_types
