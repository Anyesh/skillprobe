from typing import Any

from skillprobe.parsers.anthropic import AnthropicParser
from skillprobe.parsers.openai import OpenAIParser
from skillprobe.parsers.base import ParsedRequest, RequestParser

_PARSERS: list[RequestParser] = [AnthropicParser(), OpenAIParser()]


def parse_request(path: str, body: dict[str, Any]) -> ParsedRequest | None:
    for parser in _PARSERS:
        if parser.can_parse(path, body):
            return parser.parse(body)
    return None
