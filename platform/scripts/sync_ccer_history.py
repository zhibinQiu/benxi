#!/usr/bin/env python3
"""手动触发一次 CCER 日行情同步（写入数据库）。"""

from __future__ import annotations

import sys

from app.database import engine
from app.schema_migrate import ensure_carbon_market_schema
from app.services.carbon_market_ccer_service import sync_ccer_history_from_official


def main() -> int:
    ensure_carbon_market_schema(engine)
    n = sync_ccer_history_from_official(days=365, force_recent_days=14)
    print(f"CCER 同步完成，处理 {n} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
