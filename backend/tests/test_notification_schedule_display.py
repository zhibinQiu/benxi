from datetime import datetime, timedelta, timezone

from app.services.notification_service import (
    format_scheduled_at_local,
    preview_scheduled_display,
)


def test_preview_scheduled_display_from_scheduled_at():
    target = datetime.now(timezone.utc) + timedelta(hours=1)
    iso = target.isoformat()
    display, boost = preview_scheduled_display(scheduled_at=iso)
    assert display
    assert boost is not None
    assert boost > 3500


def test_format_scheduled_at_local_includes_seconds_when_needed():
    dt = datetime(2026, 6, 24, 15, 30, 45, tzinfo=timezone.utc)
    formatted = format_scheduled_at_local(dt)
    assert formatted.endswith(":45")
