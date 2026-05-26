from app.integrations.agent_chat_client import _workflow_sse_payload


def test_workflow_node_started_payload():
    out = _workflow_sse_payload(
        {
            "event": "node_started",
            "workflow_run_id": "run-1",
            "data": {
                "node_id": "n1",
                "title": "SQL 查询",
                "node_type": "tool",
                "index": 2,
            },
        }
    )
    assert out == {
        "phase": "node_started",
        "node_id": "n1",
        "title": "SQL 查询",
        "node_type": "tool",
        "index": 2,
    }


def test_workflow_node_finished_failed():
    out = _workflow_sse_payload(
        {
            "event": "node_finished",
            "data": {
                "node_id": "n1",
                "title": "SQL 查询",
                "status": "failed",
                "error": "timeout",
            },
        }
    )
    assert out["phase"] == "node_finished"
    assert out["status"] == "failed"
    assert out["error"] == "timeout"
