"""Pure text, ID, citation and chunking helpers."""

import re
import uuid
from datetime import datetime, timezone

from workbench.core.constants import MANAGED_FRONTMATTER_FIELDS

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid():
    return uuid.uuid4().hex


def normalize_deliverable(text):
    """Keep review state in the workbench, not in mutable Markdown metadata."""
    text = str(text)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return text
    kept = []
    for line in lines[1:closing]:
        key = line.split(":", 1)[0].strip().lower() if ":" in line else ""
        if key not in MANAGED_FRONTMATTER_FIELDS:
            kept.append(line)
    prefix = ["---", *kept, "---"] if kept else []
    return "\n".join([*prefix, *lines[closing + 1:]]).lstrip("\n")


def citation_ids(text):
    return {f"S{number}" for number in re.findall(r"\[S([1-9][0-9]*)\]", str(text))}


def tokens(text):
    lower = text.lower()
    words = re.findall(r"[a-z0-9_]+", lower)
    for part in re.findall(r"[\u4e00-\u9fff]+", lower):
        words.extend(part[i:i+2] for i in range(max(1, len(part)-1)))
    return set(words)


def chunks(text, size=1400):
    # Overlap preserves source context at paragraph/page boundaries.
    return [text[i:i+size] for i in range(0, len(text), size-160) if text[i:i+size].strip()]
