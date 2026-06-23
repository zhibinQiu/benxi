"""UUID 列表解析等通用工具。"""

from __future__ import annotations

import uuid


def parse_uuid_list(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in ids]
