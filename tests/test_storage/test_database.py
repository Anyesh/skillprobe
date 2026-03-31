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


class TestDatabaseSessions:
    def test_save_capture_with_session(self, db):
        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider="anthropic", method="POST", path="/v1/messages",
            request_body={}, status=CaptureStatus.COMPLETED,
            session="v1",
        )
        cid = db.save_capture(capture)
        retrieved = db.get_capture(cid)
        assert retrieved.session == "v1"

    def test_list_captures_by_session(self, db):
        for session in ["v1", "v1", "v2"]:
            db.save_capture(Capture(
                timestamp=datetime.now(timezone.utc),
                provider="anthropic", method="POST", path="/v1/messages",
                request_body={}, status=CaptureStatus.COMPLETED,
                session=session,
            ))
        v1_caps = db.list_captures_by_session("v1")
        assert len(v1_caps) == 2
        v2_caps = db.list_captures_by_session("v2")
        assert len(v2_caps) == 1

    def test_list_sessions(self, db):
        for session in ["v1", "v2", "v1"]:
            db.save_capture(Capture(
                timestamp=datetime.now(timezone.utc),
                provider="anthropic", method="POST", path="/v1/messages",
                request_body={}, status=CaptureStatus.COMPLETED,
                session=session,
            ))
        sessions = db.list_sessions()
        assert set(sessions) == {"v1", "v2"}

    def test_null_session_excluded_from_list(self, db):
        db.save_capture(Capture(
            timestamp=datetime.now(timezone.utc),
            provider="anthropic", method="POST", path="/v1/messages",
            request_body={}, status=CaptureStatus.COMPLETED,
        ))
        sessions = db.list_sessions()
        assert sessions == []
