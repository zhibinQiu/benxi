from __future__ import annotations

from app.api import speech as speech_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="speech_to_text",
        title="语音转写",
        description="会议录音转写、视频链接转文字、说话人区分与智能总结",
        icon="mic",
        route="/system/speech",
        router=speech_api.router,
        permission_code="feature.speech_to_text",
        permission_name="语音转写",
        enabled=True,
        category="tools",
        sort_order=15,
        grant_to_roles=("sys_admin", "member", "member"),
    )
)
