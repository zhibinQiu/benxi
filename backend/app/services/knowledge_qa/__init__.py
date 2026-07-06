"""知识检索问答域服务（按职责分子模块，对外保持原 ``knowledge_qa_service`` API）。"""

from app.services.knowledge_qa.answer import (
    _fallback_answer,
    generate_answer,
    generate_knowledge_mindmap,
)
from app.services.knowledge_qa.citations import (
    _citation_image_id,
    _citation_preview_available,
    build_aligned_qa_context_and_citations,
    build_citations,
    collapse_answer_citation_refs,
    filter_citations_for_display,
    finalize_citations_for_display,
    finalize_citations_preserving_index,
    finalize_qa_answer_and_citations,
    strip_answer_source_narrative,
)
from app.services.knowledge_qa.metadata import _doc_citation_meta, _doc_titles
from app.services.knowledge_qa.preview import (
    fetch_citation_image_bytes,
    fetch_citation_preview_bytes,
    parse_citation_bbox_param,
    resolve_citation_image_id,
)
from app.services.knowledge_qa.retrieval import (
    _filter_hits_by_version,
    _knowflow_retrieval_available,
    _knowflow_retrieve,
    _local_retrieve,
    _rag_clients_for_qa,
    _resolve_hit_platform_document_id,
    merge_nearby_retrieval_hits,
    retrieval_workflow_title,
    retrieve_hits_for_qa,
    retrieve_merged_hits_for_queries,
)
from app.services.knowledge_qa.stream import (
    answer_knowledge_question,
    iter_knowledge_qa_stream,
)
from app.services.knowledge_qa.text import strip_meta_footer as _strip_meta_footer

__all__ = [
    "answer_knowledge_question",
    "build_aligned_qa_context_and_citations",
    "build_citations",
    "collapse_answer_citation_refs",
    "fetch_citation_image_bytes",
    "fetch_citation_preview_bytes",
    "filter_citations_for_display",
    "finalize_citations_for_display",
    "finalize_citations_preserving_index",
    "finalize_qa_answer_and_citations",
    "generate_answer",
    "generate_knowledge_mindmap",
    "iter_knowledge_qa_stream",
    "merge_nearby_retrieval_hits",
    "parse_citation_bbox_param",
    "resolve_citation_image_id",
    "retrieval_workflow_title",
    "retrieve_hits_for_qa",
    "retrieve_merged_hits_for_queries",
    "strip_answer_source_narrative",
    # 测试与内部模块 patch 路径兼容
    "_citation_image_id",
    "_citation_preview_available",
    "_doc_citation_meta",
    "_doc_titles",
    "_fallback_answer",
    "_knowflow_retrieval_available",
    "_knowflow_retrieve",
    "_local_retrieve",
    "_rag_clients_for_qa",
    "_filter_hits_by_version",
    "_resolve_hit_platform_document_id",
    "_strip_meta_footer",
]
