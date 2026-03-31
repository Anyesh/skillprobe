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
    if config.skill_dirs:
        from skillprobe.analysis.skill_detector import SkillDetector
        app["skill_detector"] = SkillDetector(config.skill_dirs)
    if config.watch_test_file:
        from skillprobe.testing.loader import load_test_suite
        from skillprobe.proxy.live_assertions import LiveAssertionEvaluator
        suite = load_test_suite(config.watch_test_file)
        app["live_evaluator"] = LiveAssertionEvaluator(suite)
    app["sse_queues"] = []
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


def _resolve_forward_url(config: ProxyConfig, path: str) -> str:
    base_path = path.split("?")[0].rstrip("/")
    for prefix, attr in FORWARDING_MAP.items():
        if base_path == prefix:
            return f"{getattr(config, attr)}{path}"
    return f"{config.anthropic_api_url}{path}"


def _detect_provider(path: str) -> str:
    if "messages" in path:
        return "anthropic"
    if "chat" in path:
        return "openai"
    return "unknown"


def _extract_response_text(response_body: dict | None, provider: str) -> str:
    if not response_body:
        return ""
    if provider == "anthropic":
        parts = []
        for block in response_body.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts)
    if provider == "openai":
        choices = response_body.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
    return ""


def _reassemble_sse_response(chunks: list[bytes], provider: str) -> dict | None:
    text_parts = []
    tool_use_blocks = []
    model = None
    stop_reason = None
    usage = None

    for chunk in chunks:
        for line in chunk.decode("utf-8", errors="replace").split("\n"):
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                continue
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if provider == "anthropic":
                etype = event.get("type", "")
                if etype == "message_start":
                    msg = event.get("message", {})
                    model = msg.get("model")
                    usage = msg.get("usage")
                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text_parts.append(delta.get("text", ""))
                    elif delta.get("type") == "input_json_delta":
                        pass
                elif etype == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_use_blocks.append(block)
                elif etype == "message_delta":
                    delta = event.get("delta", {})
                    stop_reason = delta.get("stop_reason", stop_reason)
                    if event.get("usage"):
                        usage = {**(usage or {}), **event["usage"]}
            elif provider == "openai":
                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        text_parts.append(delta["content"])
                    if choices[0].get("finish_reason"):
                        stop_reason = choices[0]["finish_reason"]
                if event.get("model"):
                    model = event["model"]

    if not text_parts and not tool_use_blocks:
        return None

    if provider == "anthropic":
        content = []
        if text_parts:
            content.append({"type": "text", "text": "".join(text_parts)})
        for tb in tool_use_blocks:
            content.append(tb)
        result = {"content": content, "stop_reason": stop_reason}
        if model:
            result["model"] = model
        if usage:
            result["usage"] = usage
        return result

    return {
        "choices": [{"message": {"content": "".join(text_parts)}}],
        "model": model,
    }


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

    forward_url = _resolve_forward_url(config, path)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    provider = _detect_provider(path)
    is_stream = body.get("stream", False)

    model = body.get("model", "?")
    num_messages = len(body.get("messages", []))
    num_tools = len(body.get("tools", []))
    log.info("[%s] %s %s model=%s messages=%d tools=%d stream=%s", provider, request.method, path, model, num_messages, num_tools, is_stream)

    start_time = time.monotonic()

    if is_stream:
        return await _handle_streaming(request, client, db, forward_url, headers, raw_body, body, path, provider, start_time)
    return await _handle_buffered(request, client, db, forward_url, headers, raw_body, body, path, provider, start_time)


async def _handle_streaming(request, client, db, forward_url, headers, raw_body, body, path, provider, start_time):
    try:
        async with client.stream(request.method, forward_url, content=raw_body, headers=headers) as resp:
            response_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in HOP_BY_HOP | {"content-encoding", "content-length"}
            }
            stream_response = web.StreamResponse(status=resp.status_code, headers=response_headers)
            await stream_response.prepare(request)

            collected_chunks: list[bytes] = []
            async for chunk in resp.aiter_bytes():
                collected_chunks.append(chunk)
                await stream_response.write(chunk)

            await stream_response.write_eof()
            duration_ms = (time.monotonic() - start_time) * 1000

            response_body = _reassemble_sse_response(collected_chunks, provider)
            parsed = parse_request(path, body)
            system_chars = len(parsed.system_prompt) if parsed else 0
            sections = len(parsed.system_sections) if parsed else 0
            response_text = _extract_response_text(response_body, provider)

            detected_skills = []
            if parsed and "skill_detector" in request.app:
                detector = request.app["skill_detector"]
                matches = detector.detect(parsed.system_prompt)
                detected_skills = [{"name": m.name, "score": m.score} for m in matches]

            capture = Capture(
                timestamp=datetime.now(timezone.utc),
                provider=provider,
                method=request.method,
                path=path,
                request_body=body,
                response_body=response_body,
                response_status=resp.status_code,
                status=CaptureStatus.COMPLETED,
                parsed_data={"detected_skills": detected_skills} if detected_skills else None,
                duration_ms=duration_ms,
                session=request.app["config"].session,
            )
            capture_id = db.save_capture(capture)

            log.info(
                "  -> %d (%dms) capture=#%d system=%d chars, %d sections, response=%d chars",
                resp.status_code, duration_ms, capture_id, system_chars, sections, len(response_text),
            )
            if detected_skills:
                skill_names = ", ".join(f"{s['name']}({s['score']:.0%})" for s in detected_skills)
                log.info("  skills: [%s]", skill_names)
            if "live_evaluator" in request.app:
                evaluator = request.app["live_evaluator"]
                evaluator.evaluate(capture_id, response_text, parsed.system_prompt if parsed else "", capture.parsed_data)
            return stream_response
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


async def _handle_buffered(request, client, db, forward_url, headers, raw_body, body, path, provider, start_time):
    try:
        resp = await client.request(method=request.method, url=forward_url, content=raw_body, headers=headers)
        duration_ms = (time.monotonic() - start_time) * 1000

        response_body = None
        try:
            response_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            pass

        parsed = parse_request(path, body)
        system_chars = len(parsed.system_prompt) if parsed else 0
        sections = len(parsed.system_sections) if parsed else 0
        response_text = _extract_response_text(response_body, provider)

        detected_skills = []
        if parsed and "skill_detector" in request.app:
            detector = request.app["skill_detector"]
            matches = detector.detect(parsed.system_prompt)
            detected_skills = [{"name": m.name, "score": m.score} for m in matches]

        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider=provider,
            method=request.method,
            path=path,
            request_body=body,
            response_body=response_body,
            response_status=resp.status_code,
            status=CaptureStatus.COMPLETED,
            parsed_data={"detected_skills": detected_skills} if detected_skills else None,
            duration_ms=duration_ms,
            session=request.app["config"].session,
        )
        capture_id = db.save_capture(capture)

        log.info(
            "  -> %d (%dms) capture=#%d system=%d chars, %d sections, response=%d chars",
            resp.status_code, duration_ms, capture_id, system_chars, sections, len(response_text),
        )
        if detected_skills:
            skill_names = ", ".join(f"{s['name']}({s['score']:.0%})" for s in detected_skills)
            log.info("  skills: [%s]", skill_names)
        if "live_evaluator" in request.app:
            evaluator = request.app["live_evaluator"]
            evaluator.evaluate(capture_id, response_text, parsed.system_prompt if parsed else "", capture.parsed_data)

        response_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in HOP_BY_HOP | {"content-encoding", "content-length"}
        }
        return web.Response(status=resp.status_code, body=resp.content, headers=response_headers)
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
