import pytest
from datetime import datetime, timezone

from skillprobe.storage.database import Database
from skillprobe.storage.models import Capture, CaptureStatus


@pytest.fixture
def db(tmp_db):
    database = Database(tmp_db)
    database.initialize()
    yield database
    database.close()


class TestDatabaseInit:
    def test_creates_tables(self, db):
        tables = db.list_tables()
        assert "captures" in tables

    def test_idempotent_init(self, db):
        db.initialize()
        tables = db.list_tables()
        assert "captures" in tables


class TestDatabaseCaptures:
    def test_save_and_get_capture(self, db):
        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider="anthropic",
            method="POST",
            path="/v1/messages",
            request_body={"model": "claude-sonnet-4-6-20250514", "messages": []},
            status=CaptureStatus.COMPLETED,
            response_status=200,
        )
        capture_id = db.save_capture(capture)
        assert capture_id > 0

        retrieved = db.get_capture(capture_id)
        assert retrieved is not None
        assert retrieved.provider == "anthropic"
        assert retrieved.request_body["model"] == "claude-sonnet-4-6-20250514"

    def test_list_captures(self, db):
        for i in range(3):
            db.save_capture(Capture(
                timestamp=datetime.now(timezone.utc),
                provider="anthropic",
                method="POST",
                path="/v1/messages",
                request_body={"model": f"model-{i}"},
                status=CaptureStatus.COMPLETED,
            ))
        captures = db.list_captures(limit=10)
        assert len(captures) == 3

    def test_list_captures_with_limit(self, db):
        for i in range(5):
            db.save_capture(Capture(
                timestamp=datetime.now(timezone.utc),
                provider="anthropic",
                method="POST",
                path="/v1/messages",
                request_body={},
                status=CaptureStatus.COMPLETED,
            ))
        captures = db.list_captures(limit=2)
        assert len(captures) == 2

    def test_list_captures_filter_by_provider(self, db):
        db.save_capture(Capture(
            timestamp=datetime.now(timezone.utc), provider="anthropic",
            method="POST", path="/v1/messages", request_body={}, status=CaptureStatus.COMPLETED,
        ))
        db.save_capture(Capture(
            timestamp=datetime.now(timezone.utc), provider="openai",
            method="POST", path="/v1/chat/completions", request_body={}, status=CaptureStatus.COMPLETED,
        ))
        anthropic_only = db.list_captures(provider="anthropic")
        assert len(anthropic_only) == 1
        assert anthropic_only[0].provider == "anthropic"
