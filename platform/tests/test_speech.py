"""Speech-to-text API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.speech import SpeechSegmentIn
from app.services.speech_service import merge_consecutive_speaker_segments


def test_speech_meta(client, admin_token):
    r = client.get(
        "/api/v1/speech/meta",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "configured" in data
    assert "provider" in data
    assert ".webm" in data["accepted_extensions"]


@patch("app.services.speech_service.transcribe", new_callable=AsyncMock)
def test_speech_transcribe_success(mock_transcribe, client, admin_token):
    from app.schemas.speech import SpeechSegmentOut, SpeechTranscribeOut

    mock_transcribe.return_value = SpeechTranscribeOut(
        text="你好世界",
        language="zh",
        duration_seconds=1.2,
        model="funasr/paraformer-zh+cam++",
        segments=[
            SpeechSegmentOut(speaker="说话人 1", start=0.0, end=1.2, text="你好世界")
        ],
    )
    r = client.post(
        "/api/v1/speech/transcribe",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("clip.webm", b"\x00\x01", "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["text"] == "你好世界"
    assert len(r.json()["data"]["segments"]) == 1


@patch("app.integrations.deepseek_client.summarize_text", new_callable=AsyncMock)
def test_speech_summarize(mock_summarize, client, admin_token):
    mock_summarize.return_value = {
        "summary": "会议讨论了项目进度。",
        "model": "deepseek-chat",
    }
    with patch("app.integrations.deepseek_client.is_configured", return_value=True):
        r = client.post(
            "/api/v1/speech/summarize",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"text": "今天开会讨论了项目进度，决定下周交付。", "style": "brief"},
        )
    assert r.status_code == 200, r.text
    assert "项目进度" in r.json()["data"]["summary"]


def test_merge_consecutive_speaker_segments():
    segs = [
        SpeechSegmentIn(speaker="A", start=0, end=5, text="你好"),
        SpeechSegmentIn(speaker="A", start=5, end=10, text="世界"),
        SpeechSegmentIn(speaker="B", start=10, end=15, text="嗯"),
    ]
    merged = merge_consecutive_speaker_segments(segs)
    assert len(merged) == 2
    assert merged[0]["speaker"] == "A"
    assert merged[0]["text"] == "你好 世界"
    assert merged[0]["end"] == 10
    assert merged[1]["speaker"] == "B"


@patch("app.integrations.deepseek_client.summarize_speaker_timeline", new_callable=AsyncMock)
def test_speech_summarize_with_segments(mock_timeline, client, admin_token):
    mock_timeline.return_value = {
        "summary": '[{"speaker":"A","start":0,"end":10,"time_range":"0:00–0:10","summary":"问候"}]',
        "model": "deepseek-chat",
    }
    with patch("app.integrations.deepseek_client.is_configured", return_value=True):
        r = client.post(
            "/api/v1/speech/summarize",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "text": "",
                "style": "brief",
                "segments": [
                    {"speaker": "A", "start": 0, "end": 5, "text": "你好"},
                    {"speaker": "A", "start": 5, "end": 10, "text": "世界"},
                ],
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["blocks"]
    assert data["blocks"][0]["speaker"] == "A"
    assert "问候" in data["blocks"][0]["summary"]


def test_meeting_record_save_and_list(client, admin_token):
    payload = {
        "title": "测试会议",
        "segments": [
            {"speaker": "说话人 1", "start": 0, "end": 2, "text": "大家好"},
        ],
        "summary": "开场问候",
    }
    r = client.post(
        "/api/v1/speech/records",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert r.status_code == 200, r.text
    rec_id = r.json()["data"]["id"]

    r2 = client.get(
        "/api/v1/speech/records",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 200
    items = r2.json()["data"]["items"]
    assert any(i["id"] == rec_id for i in items)

    r3 = client.get(
        f"/api/v1/speech/records/{rec_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["title"] == "测试会议"
    assert len(r3.json()["data"]["segments"]) == 1

    r4 = client.delete(
        f"/api/v1/speech/records/{rec_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r4.status_code == 200
