"""Prompt builders (docs/spec.md S6.8)."""

from django.conf import settings

from agent import prompts
from agent.event_types import load_event_types


def test_every_prompt_asks_for_a_single_json_object() -> None:
    # Some models answer with a bare list when there is only one item, which fails validation.
    event_types = load_event_types(settings.EVENT_TYPES_FILE)
    candidates = [{"id": "c1", "event_type": "missing_ppe", "time_s": 1.0, "reason": "r"}]
    built = [
        prompts.survey_prompt(event_types, []),
        prompts.inspect_prompt(event_types, [], "question"),
        prompts.verify_prompt(event_types, candidates, []),
        prompts.report_prompt(event_types, [], [], [], None),
    ]

    for prompt in built:
        assert "Reply with a single JSON object (not a list)" in prompt
