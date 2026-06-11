"""结构化分块级版本 diff（含页码 / bbox 锚点）。"""

from __future__ import annotations

import difflib
import uuid

from sqlalchemy.orm import Session

from app.models.document import DocumentVersion
from app.models.document_version_block import DocumentVersionBlock
from app.services.document_version_block_service import ensure_version_blocks


def _anchor_from_block(
    block: DocumentVersionBlock | None,
    *,
    version_id: uuid.UUID,
    side: str,
) -> dict | None:
    if not block:
        return None
    return {
        "side": side,
        "version_id": str(version_id),
        "block_index": block.block_index,
        "page": block.page,
        "bbox": block.bbox,
        "block_type": block.block_type,
    }


def _anchors_from_blocks(
    blocks: list[DocumentVersionBlock],
    *,
    version_id: uuid.UUID,
    side: str,
) -> list[dict]:
    return [
        {
            "side": side,
            "version_id": str(version_id),
            "block_index": b.block_index,
            "page": b.page,
            "bbox": b.bbox,
            "block_type": b.block_type,
        }
        for b in blocks
    ]


def _inline_spans(left: str | None, right: str | None) -> list[dict]:
    """块内行级 diff，供前端细粒度高亮。"""
    if not left or not right or left == right:
        return []
    spans: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, left, right).get_opcodes():
        if tag == "equal":
            continue
        spans.append(
            {
                "tag": tag,
                "left_start": i1,
                "left_end": i2,
                "right_start": j1,
                "right_end": j2,
            }
        )
    return spans


def compute_block_diffs(
    db: Session,
    from_version: DocumentVersion,
    to_version: DocumentVersion,
) -> tuple[list[dict], dict]:
    left_blocks = ensure_version_blocks(db, from_version)
    right_blocks = ensure_version_blocks(db, to_version)

    left_texts = [b.text for b in left_blocks]
    right_texts = [b.text for b in right_blocks]
    matcher = difflib.SequenceMatcher(None, left_texts, right_texts)

    items: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        lb = left_blocks[i1:i2]
        rb = right_blocks[j1:j2]
        text_left = "\n\n".join(b.text for b in lb).strip() or None
        text_right = "\n\n".join(b.text for b in rb).strip() or None
        if tag == "delete":
            dtype = "delete"
        elif tag == "insert":
            dtype = "add"
        else:
            dtype = "modify"

        anchor = {
            "kind": "block",
            "left": _anchor_from_block(lb[0] if lb else None, version_id=from_version.id, side="left"),
            "right": _anchor_from_block(rb[0] if rb else None, version_id=to_version.id, side="right"),
            "left_blocks": _anchors_from_blocks(lb, version_id=from_version.id, side="left"),
            "right_blocks": _anchors_from_blocks(rb, version_id=to_version.id, side="right"),
        }
        if dtype == "modify" and text_left and text_right:
            anchor["inline_spans"] = _inline_spans(text_left, text_right)

        items.append(
            {
                "diff_type": dtype,
                "text_left": text_left,
                "text_right": text_right,
                "anchor_json": anchor,
            }
        )

    meta = {
        "engine": "block",
        "from_version_no": from_version.version_no,
        "to_version_no": to_version.version_no,
        "from_block_count": len(left_blocks),
        "to_block_count": len(right_blocks),
    }
    return items, meta
