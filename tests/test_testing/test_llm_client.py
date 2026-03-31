import pytest
from aiohttp import web

from skillprobe.testing.llm_client import HttpLLMClient


async def fake_anthropic(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response({
        "content": [{"type": "text", "text": f"Echo: {body['messages'][0]['content']}"}],
        "stop_reason": "end_turn",
    })


async def fake_openai(request: web.Request) -> web.Response:
    body = await request.json()
    return web.json_response({
        "choices": [{"message": {"content": f"Echo: {body['messages'][-1]['content']}"}}],
    })


@pytest.fixture
async def anthropic_server(aiohttp_server):
    app = web.Application()
    app.router.add_post("/v1/messages", fake_anthropic)
    return await aiohttp_server(app)


@pytest.fixture
async def openai_server(aiohttp_server):
    app = web.Application()
    app.router.add_post("/v1/chat/completions", fake_openai)
    return await aiohttp_server(app)


class TestAnthropicClient:
    @pytest.mark.asyncio
    async def test_calls_anthropic(self, anthropic_server):
        client = HttpLLMClient(
            anthropic_base_url=f"http://localhost:{anthropic_server.port}",
            anthropic_api_key="test-key",
        )
        result = await client.call(
            system="You are helpful.",
            message="hello",
            model="claude-haiku-4-5-20251001",
            provider="anthropic",
        )
        assert "Echo: hello" in result
        await client.close()


class TestOpenAIClient:
    @pytest.mark.asyncio
    async def test_calls_openai(self, openai_server):
        client = HttpLLMClient(
            openai_base_url=f"http://localhost:{openai_server.port}",
            openai_api_key="test-key",
        )
        result = await client.call(
            system="You are helpful.",
            message="hello",
            model="gpt-4o",
            provider="openai",
        )
        assert "Echo: hello" in result
        await client.close()
