from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ParsedTool:
    name: str
    description: str
    parameters: dict[str, Any] | None = None


@dataclass
class ParsedMessage:
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class SystemPromptSection:
    title: str
    content: str
    start_offset: int
    end_offset: int


@dataclass
class ParsedRequest:
    provider: str
    model: str
    system_prompt: str
    system_sections: list[SystemPromptSection]
    messages: list[ParsedMessage]
    tools: list[ParsedTool]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    raw_system: Any = None


class RequestParser(Protocol):
    def can_parse(self, path: str, body: dict[str, Any]) -> bool: ...
    def parse(self, body: dict[str, Any]) -> ParsedRequest: ...
