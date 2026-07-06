"""AIP 身份凭证 — 自 agentkit-aip 再导出。"""

from agentkit_aip.auth import (
    SK_PREFIX,
    generate_aip_sk,
    hash_aip_sk,
    is_aip_sk_token,
    sk_display_prefix,
)

__all__ = [
    "SK_PREFIX",
    "generate_aip_sk",
    "hash_aip_sk",
    "is_aip_sk_token",
    "sk_display_prefix",
]
