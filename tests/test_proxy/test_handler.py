import json

import pytest
from aiohttp import web

from skillprobe.config import ProxyConfig
from skillprobe.proxy.handler import create_app
from skillprobe.storage.database import Database


async def fake_anthropic_handler(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response({
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from fake API"}],
        "model": body.get("model", "unknown"),
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


@pytest.fixture
async def fake_api_server(aiohttp_server):
    app = web.Application()
    app.router.add_post("/v1/messages", fake_anthropic_handler)
    server = await aiohttp_server(app)
    return server


@pytest.fixture
async def proxy_app(tmp_db, fake_api_server):
    config = ProxyConfig(
        db_path=tmp_db,
        anthropic_api_url=f"http://localhost:{fake_api_server.port}",
    )
    db = Database(config.db_path)
    db.initialize()
    app = create_app(config, db)
    yield app
    db.close()


class TestProxyHealth:
    async def test_health_endpoint(self, aiohttp_client, proxy_app):
        client = await aiohttp_client(proxy_app)
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"


class TestProxyForwarding:
    async def test_forwards_anthropic_request(self, aiohttp_client, proxy_app):
        client = await aiohttp_client(proxy_app)
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6-20250514",
                "max_tokens": 100,
                "system": "You are helpful.",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["content"][0]["text"] == "Hello from fake API"


class TestProxyCapture:
    async def test_captures_request_in_database(self, aiohttp_client, proxy_app, tmp_db):
        client = await aiohttp_client(proxy_app)
        await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6-20250514",
                "system": "Test system prompt.",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"x-api-key": "test-key"},
        )
        db = Database(tmp_db)
        db.initialize()
        captures = db.list_captures()
        assert len(captures) == 1
        assert captures[0].provider == "anthropic"
        assert captures[0].request_body["system"] == "Test system prompt."
        db.close()
