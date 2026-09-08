from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable
from typing import Any

from .models import Chunk


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return str(uuid.UUID(hex=digest[:32]))


def _split_long_text(text: str, max_chars: int = 1800) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    result: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) + 2 > max_chars:
            result.append("\n\n".join(current))
            current = []
            current_len = 0
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[。！？.!?；;])", paragraph)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if current and current_len + len(sentence) > max_chars:
                    result.append("".join(current))
                    current = []
                    current_len = 0
                current.append(sentence)
                current_len += len(sentence)
        else:
            current.append(paragraph)
            current_len += len(paragraph) + 2
    if current:
        result.append("\n\n".join(current))
    return result


def chunk_markdown(
    source_id: str,
    text: str,
    title: str,
    metadata: dict[str, Any],
) -> list[Chunk]:
    headings: list[str] = []
    current_lines: list[str] = []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            locator = " > ".join(headings) if headings else title
            sections.append((locator, body))
        current_lines.clear()

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            headings[level - 1 :] = [heading]
        else:
            current_lines.append(line)
    flush()

    if not sections and text.strip():
        sections = [(title, text.strip())]

    chunks: list[Chunk] = []
    for locator, body in sections:
        for index, part in enumerate(_split_long_text(body)):
            chunk_locator = locator if index == 0 else f"{locator} / part {index + 1}"
            enriched = f"{title}\n{chunk_locator}\n\n{part}".strip()
            chunk_id = _stable_id(source_id, chunk_locator, part)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    text=enriched,
                    title=title,
                    locator=chunk_locator,
                    metadata=dict(metadata),
                )
            )
    return chunks


def chunk_pdf_pages(
    source_id: str,
    pages: Iterable[tuple[int, str]],
    title: str,
    metadata: dict[str, Any],
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, text in pages:
        for index, part in enumerate(_split_long_text(text)):
            locator = f"page {page_number}"
            if index:
                locator += f" / part {index + 1}"
            enriched = f"{title}\n{locator}\n\n{part}".strip()
            chunks.append(
                Chunk(
                    chunk_id=_stable_id(source_id, locator, part),
                    source_id=source_id,
                    text=enriched,
                    title=title,
                    locator=locator,
                    metadata=dict(metadata),
                )
            )
    return chunks
