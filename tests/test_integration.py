import pytest
from aiohttp import web

from skillprobe.config import ProxyConfig
from skillprobe.proxy.handler import create_app
from skillprobe.storage.database import Database
from skillprobe.parsers import parse_request


async def fake_api(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response({
        "id": "msg_integration",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Use parameterized queries to prevent SQL injection."}],
        "model": body.get("model"),
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    })


@pytest.fixture
async def fake_api_server(aiohttp_server):
    app = web.Application()
    app.router.add_post("/v1/messages", fake_api)
    return await aiohttp_server(app)


@pytest.fixture
async def running_proxy(tmp_db, fake_api_server, aiohttp_client):
    config = ProxyConfig(
        db_path=tmp_db,
        anthropic_api_url=f"http://localhost:{fake_api_server.port}",
    )
    db = Database(config.db_path)
    db.initialize()
    app = create_app(config, db)
    client = await aiohttp_client(app)
    yield client, db
    db.close()


class TestEndToEnd:
    async def test_full_flow_capture_and_parse(self, running_proxy):
        client, db = running_proxy

        resp = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6-20250514",
                "max_tokens": 1024,
                "system": "You are a security-focused assistant.\n\n## Skill: secure-code\nAlways check for SQL injection.",
                "messages": [{"role": "user", "content": "write a login function"}],
                "tools": [
                    {"name": "read_file", "description": "Read a file", "input_schema": {"type": "object"}},
                ],
            },
            headers={"x-api-key": "test"},
        )
        assert resp.status == 200

        captures = db.list_captures()
        assert len(captures) == 1

        capture = captures[0]
        assert capture.provider == "anthropic"
        assert capture.response_status == 200

        parsed = parse_request(capture.path, capture.request_body)
        assert parsed.model == "claude-sonnet-4-6-20250514"
        assert "secure-code" in parsed.system_prompt
        assert len(parsed.tools) == 1
        assert parsed.tools[0].name == "read_file"
        section_titles = [s.title for s in parsed.system_sections]
        assert "## Skill: secure-code" in section_titles

    async def test_multiple_captures_counted(self, running_proxy):
        client, db = running_proxy
        for _ in range(3):
            await client.post(
                "/v1/messages",
                json={"model": "claude-haiku-4-5-20251001", "messages": [{"role": "user", "content": "hi"}]},
                headers={"x-api-key": "test"},
            )
        captures = db.list_captures()
        assert len(captures) == 3
