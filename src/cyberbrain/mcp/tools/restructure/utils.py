"""Shared utility helpers for the restructure package."""

import json


def _repair_json(raw: str) -> list:
    """Try to parse raw as JSON array, with lightweight repair on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting complete JSON objects from a partial/truncated array
    repaired = raw.strip()
    if not repaired.startswith("["):
        repaired = "[" + repaired
    # Close any unclosed brackets/braces
    opens = repaired.count("{") - repaired.count("}")
    closes = repaired.count("[") - repaired.count("]")
    if opens > 0:
        repaired += "}" * opens
    if closes > 0:
        repaired += "]" * closes
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: extract all complete {...} objects from the string
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(raw[start : i + 1])
                    objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    if objects:
        return objects

    raise json.JSONDecodeError("Could not repair JSON", raw, 0)
