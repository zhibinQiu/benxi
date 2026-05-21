"""Export paragraph text from BabelDOC IL JSON (il_translated.json)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def default_il_cache_path(pdf_stem: str) -> Path:
    return Path.home() / ".cache" / "babeldoc" / "working" / pdf_stem / "il_translated.json"


def _collect_il_candidates(
    pdf_stem: str,
    *,
    babeldoc_working_root: Path | None = None,
    search_roots: list[Path] | None = None,
) -> list[Path]:
    roots: list[Path] = []
    if babeldoc_working_root is not None:
        roots.append(Path(babeldoc_working_root))
    if search_roots:
        roots.extend(Path(r) for r in search_roots)

    cache_working = Path.home() / ".cache" / "babeldoc" / "working"
    roots.extend([cache_working, cache_working / pdf_stem])

    found: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen or not resolved.is_file():
            return
        seen.add(resolved)
        found.append(resolved)

    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        add(root / "il_translated.json")
        add(root / pdf_stem / "il_translated.json")
        try:
            for path in root.rglob("il_translated.json"):
                add(path)
        except OSError as e:
            logger.debug("rglob failed under %s: %s", root, e)

    return found


def resolve_il_translated_path(
    pdf_stem: str,
    babeldoc_working_root: Path | None = None,
    *,
    search_roots: list[Path] | None = None,
) -> Path | None:
    """Find il_translated.json written by BabelDOC when debug=True."""
    candidates = _collect_il_candidates(
        pdf_stem,
        babeldoc_working_root=babeldoc_working_root,
        search_roots=search_roots,
    )
    if not candidates:
        return None

    stem_matches = [p for p in candidates if pdf_stem in p.parts]
    pool = stem_matches or candidates
    return max(pool, key=lambda p: p.stat().st_mtime)


def snapshot_il_translated(
    pdf_stem: str,
    dest_dir: Path,
    *,
    babeldoc_working_root: Path | None = None,
    search_roots: list[Path] | None = None,
) -> Path | None:
    """Copy il_translated.json into dest_dir for stable later export."""
    src = resolve_il_translated_path(
        pdf_stem,
        babeldoc_working_root,
        search_roots=search_roots,
    )
    if src is None:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{pdf_stem}.il_translated.json"
    shutil.copy2(src, dest)
    return dest


def iter_paragraphs(doc: dict):
    for page_index, page in enumerate(doc.get("page", []), start=1):
        for paragraph_index, paragraph in enumerate(
            page.get("pdf_paragraph", []), start=1
        ):
            text = (paragraph.get("unicode") or "").strip()
            if not text:
                continue
            yield {
                "page": page_index,
                "paragraph": paragraph_index,
                "text": text,
                "debug_id": paragraph.get("debug_id"),
            }


def to_export_payload(source: Path, doc: dict) -> dict:
    return {
        "source_il": str(source.resolve()),
        "pages": doc.get("total_page_count") or len(doc.get("page", [])),
        "paragraphs": list(iter_paragraphs(doc)),
    }


def to_markdown(payload: dict, *, title: str = "提取文本") -> str:
    lines: list[str] = [f"# {title}", ""]
    lines.append(f"- 页数: {payload['pages']}")
    lines.append(f"- 段落数: {len(payload['paragraphs'])}")
    lines.append("")

    current_page: int | None = None
    for item in payload["paragraphs"]:
        if item["page"] != current_page:
            current_page = item["page"]
            lines.append(f"## 第 {current_page} 页")
            lines.append("")
        lines.append(item["text"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def payload_from_pdf(pdf_path: Path) -> dict:
    """Fallback: extract plain text per page from translated PDF."""
    try:
        import pymupdf
    except ImportError as e:
        raise RuntimeError("pymupdf is required for PDF text fallback") from e

    doc = pymupdf.open(pdf_path)
    paragraphs: list[dict] = []
    page_count = doc.page_count
    try:
        for page_index in range(page_count):
            text = (doc[page_index].get_text() or "").strip()
            if not text:
                continue
            paragraphs.append(
                {
                    "page": page_index + 1,
                    "paragraph": 1,
                    "text": text,
                    "debug_id": None,
                }
            )
    finally:
        doc.close()

    return {
        "source_il": str(pdf_path.resolve()),
        "pages": page_count,
        "paragraphs": paragraphs,
        "export_mode": "pdf_text_fallback",
    }


def write_extracted_exports(
    pdf_stem: str,
    output_dir: Path,
    *,
    babeldoc_working_root: Path | None = None,
    search_roots: list[Path] | None = None,
    mono_pdf_path: Path | str | None = None,
) -> dict[str, str]:
    """Write JSON and Markdown exports; returns download path map keys."""
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = output_dir / f"{pdf_stem}.il_translated.json"
    il_path: Path | None = None
    if snapshot.is_file():
        il_path = snapshot
    else:
        il_path = resolve_il_translated_path(
            pdf_stem,
            babeldoc_working_root,
            search_roots=search_roots,
        )

    if il_path is not None:
        with il_path.open(encoding="utf-8") as f:
            doc = json.load(f)
        payload = to_export_payload(il_path, doc)
        title = "提取文本（译文段落）"
    elif mono_pdf_path and Path(mono_pdf_path).is_file():
        payload = payload_from_pdf(Path(mono_pdf_path))
        title = "提取文本（PDF 按页回退）"
        logger.info(
            "il_translated.json not found for %s; using PDF text fallback",
            pdf_stem,
        )
    else:
        return {}

    base = pdf_stem
    json_path = output_dir / f"{base}-extracted.json"
    md_path = output_dir / f"{base}-extracted.md"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        to_markdown(payload, title=title),
        encoding="utf-8",
    )
    return {"extracted-json": str(json_path), "extracted-md": str(md_path)}
