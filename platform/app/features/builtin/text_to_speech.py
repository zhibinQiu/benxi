"""语音合成 — 硅基流动。"""

from __future__ import annotations

from app.api import text_to_speech as text_to_speech_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="text_to_speech",
        title="语音合成",
        description="文本转自然语音，支持多音色与情感表达。",
        icon="volume-high",
        route="/system/text-to-speech",
        router=text_to_speech_api.router,
        permission_code="feature.text_to_speech",
        permission_name="语音合成",
        enabled=True,
        category="tools",
        sort_order=16,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
