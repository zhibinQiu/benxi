from __future__ import annotations

import uuid
from typing import Protocol


class ParseProvider(Protocol):
    """Extract structured text from documents (e.g. PaddleOCR)."""

    def schedule_parse(self, document_id: uuid.UUID, version_id: uuid.UUID) -> None:
        ...


class IndexProvider(Protocol):
    """Index document chunks for RAG (e.g. KnowFlow)."""

    def schedule_index(self, document_id: uuid.UUID, version_id: uuid.UUID) -> None:
        ...


class NoOpParseProvider:
    def schedule_parse(self, document_id: uuid.UUID, version_id: uuid.UUID) -> None:
        return None


class NoOpIndexProvider:
    def schedule_index(self, document_id: uuid.UUID, version_id: uuid.UUID) -> None:
        return None
