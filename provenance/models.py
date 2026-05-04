from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Decision:
    """A single architectural decision captured from the codebase history."""

    content: str          # One-sentence description of the decision
    why: str              # The reasoning behind it
    source_type: str      # commit | pr | adr | ticket | comment
    source_ref: str       # commit hash, PR number, ADR filename, etc.
    source_author: str    # Who made the decision
    file_paths: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    ingested_at: datetime = field(default_factory=_now)
    valid_until: datetime | None = None
    confidence: float = 0.8
    id: str = field(default_factory=_uuid)

    def is_stale(self) -> bool:
        if self.valid_until is None:
            return False
        return _now() > self.valid_until

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "why": self.why,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "source_author": self.source_author,
            "file_paths": self.file_paths,
            "keywords": self.keywords,
            "created_at": self.created_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "confidence": self.confidence,
        }

    @property
    def short_ref(self) -> str:
        return self.source_ref[:8] if len(self.source_ref) > 8 else self.source_ref

    def __str__(self) -> str:
        return f"[{self.source_type}:{self.short_ref}] {self.content}"
