import json
import logging
import time
from datetime import datetime, timezone

import httpx
from aiohttp import web

from skillprobe.config import ProxyConfig
from skillprobe.parsers import parse_request
from skillprobe.storage.database import Database
from skillprobe.storage.models import Capture, CaptureStatus

log = logging.getLogger("skillprobe.proxy")

FORWARDING_MAP = {
    "/v1/messages": "anthropic_api_url",
    "/v1/chat/completions": "openai_api_url",
}

HOP_BY_HOP = {"host", "transfer-encoding", "connection", "keep-alive", "upgrade"}


def create_app(config: ProxyConfig, db: Database) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["db"] = db
    app["http_client"] = httpx.AsyncClient(timeout=120.0)
    app.router.add_get("/health", handle_health)
    app.router.add_route("*", "/{path:.*}", handle_proxy)
    app.on_cleanup.append(cleanup)
    return app


async def cleanup(app: web.Application):
    await app["http_client"].aclose()


async def handle_health(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    captures = db.list_captures(limit=10000)
    return web.json_response({
        "status": "ok",
        "total_captures": len(captures),
    })


async def handle_proxy(request: web.Request) -> web.Response:
    config: ProxyConfig = request.app["config"]
    db: Database = request.app["db"]
    client: httpx.AsyncClient = request.app["http_client"]

    path = "/" + request.match_info["path"]
    raw_body = await request.read()
    body = {}
    if raw_body:
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            pass

    base_path = path.split("?")[0].rstrip("/")
    target_attr = None
    for prefix, attr in FORWARDING_MAP.items():
        if base_path == prefix:
            target_attr = attr
            break

    if target_attr is None:
        target_url_base = config.anthropic_api_url
    else:
        target_url_base = getattr(config, target_attr)

    forward_url = f"{target_url_base}{path}"
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    provider = "anthropic" if "messages" in path else "openai" if "chat" in path else "unknown"

    model = body.get("model", "?")
    num_messages = len(body.get("messages", []))
    num_tools = len(body.get("tools", []))
    log.info("[%s] %s %s model=%s messages=%d tools=%d", provider, request.method, path, model, num_messages, num_tools)

    start_time = time.monotonic()
    try:
        resp = await client.request(
            method=request.method,
            url=forward_url,
            content=raw_body,
            headers=headers,
        )
        duration_ms = (time.monotonic() - start_time) * 1000

        response_body = None
        try:
            response_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            pass

        parsed = parse_request(path, body)
        system_chars = len(parsed.system_prompt) if parsed else 0
        sections = len(parsed.system_sections) if parsed else 0
        tool_names = ", ".join(t.name for t in parsed.tools[:5]) if parsed else ""

        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider=provider,
            method=request.method,
            path=path,
            request_body=body,
            response_body=response_body,
            response_status=resp.status_code,
            status=CaptureStatus.COMPLETED,
            parsed_data=None,
            duration_ms=duration_ms,
        )
        capture_id = db.save_capture(capture)

        log.info(
            "  -> %d (%dms) capture=#%d system=%d chars, %d sections, tools=[%s]",
            resp.status_code, duration_ms, capture_id, system_chars, sections, tool_names,
        )

        response_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in HOP_BY_HOP | {"content-encoding", "content-length"}
        }
        return web.Response(
            status=resp.status_code,
            body=resp.content,
            headers=response_headers,
        )
    except httpx.HTTPError as e:
        duration_ms = (time.monotonic() - start_time) * 1000
        log.error("  -> FAILED (%dms): %s", duration_ms, e)
        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider=provider,
            method=request.method,
            path=path,
            request_body=body,
            status=CaptureStatus.FAILED,
            parsed_data=None,
            duration_ms=duration_ms,
        )
        db.save_capture(capture)
        return web.json_response({"error": str(e)}, status=502)
