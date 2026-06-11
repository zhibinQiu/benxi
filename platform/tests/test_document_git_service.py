"""Git 版本 diff 解析与对比。"""

from __future__ import annotations

import shutil

import pytest

from app.services.document_git_service import parse_git_unified_diff


@pytest.mark.skipif(not shutil.which("git"), reason="git not installed")
def test_parse_git_unified_diff():
    sample = """diff --git a/content.txt b/content.txt
index 111..222 100644
--- a/content.txt
+++ b/content.txt
@@ -1,2 +1,3 @@
 line one
-line two
+line two changed
+line three
"""
    items = parse_git_unified_diff(sample)
    assert len(items) == 1
    assert items[0]["diff_type"] == "modify"
    assert "line two" in (items[0]["text_left"] or "")
    assert "line two changed" in (items[0]["text_right"] or "")


def test_parse_git_unified_diff_empty():
    assert parse_git_unified_diff("") == []
