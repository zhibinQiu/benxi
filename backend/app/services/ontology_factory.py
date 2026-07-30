"""OntologyService 工厂 — 供 API / 语义层 / KgService 统一获取。"""

from __future__ import annotations

from app.services.ontology_service import OntologyService, get_ontology_service

__all__ = ["OntologyService", "get_ontology_service"]
