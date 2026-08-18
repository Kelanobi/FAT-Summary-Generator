from __future__ import annotations

import re


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def value_after_label(text: str, label: str) -> str | None:
    lines = clean_lines(text)
    normalized = label.casefold()
    for index, line in enumerate(lines):
        if line.casefold() == normalized and index + 1 < len(lines):
            return lines[index + 1]
    return None


def first_match(text: str, pattern: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return match.group(1).strip()

