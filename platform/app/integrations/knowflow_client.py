"""KnowFlow client stub — swap for HTTP client when KNOWFLOW_ENABLED=true."""

from __future__ import annotations

from app.config import get_settings
from app.integrations.text_extract import ParsedDocument, local_search


class StubKnowFlowClient:
    def enabled(self) -> bool:
        return False

    def parse_document(self, *args, **kwargs) -> ParsedDocument:
        raise RuntimeError("KnowFlow 未启用，使用平台 CPU 解析")

    def retrieve(
        self,
        parsed_docs: list[ParsedDocument],
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        allowed = set(document_ids or [])
        docs = parsed_docs
        if allowed:
            docs = [d for d in parsed_docs if str(d.document_id) in allowed]
        return local_search(docs, query, limit=limit)


def get_knowflow_client() -> StubKnowFlowClient:
    settings = get_settings()
    if getattr(settings, "knowflow_enabled", False):
        # Future: return HttpKnowFlowClient(settings.knowflow_base_url, ...)
        pass
    return StubKnowFlowClient()
