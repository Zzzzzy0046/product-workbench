from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceDocument:
    source_id: str
    path: Path
    metadata: dict[str, Any]
    enabled: bool = True


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    text: str
    title: str
    locator: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            **self.metadata,
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "title": self.title,
            "locator": self.locator,
            "text": self.text,
        }
