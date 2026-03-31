from typing import Any

from skillprobe.parsers.base import (
    ParsedMessage,
    ParsedRequest,
    ParsedTool,
    SystemPromptSection,
)


class AnthropicParser:
    def can_parse(self, path: str, body: dict[str, Any]) -> bool:
        return path.split("?")[0].rstrip("/") == "/v1/messages"

    def parse(self, body: dict[str, Any]) -> ParsedRequest:
        system_prompt, raw_system = self._extract_system(body.get("system"))
        return ParsedRequest(
            provider="anthropic",
            model=body.get("model", "unknown"),
            system_prompt=system_prompt,
            system_sections=self._extract_sections(system_prompt),
            messages=self._extract_messages(body.get("messages", [])),
            tools=self._extract_tools(body.get("tools", [])),
            max_tokens=body.get("max_tokens"),
            temperature=body.get("temperature"),
            stream=body.get("stream", False),
            raw_system=raw_system,
        )

    def _extract_system(self, system: Any) -> tuple[str, Any]:
        if system is None:
            return "", None
        if isinstance(system, str):
            return system, system
        if isinstance(system, list):
            parts = []
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block["text"])
            return "\n\n".join(parts), system
        return str(system), system

    def _extract_sections(self, text: str) -> list[SystemPromptSection]:
        if not text:
            return []
        sections = []
        lines = text.split("\n")
        offset = 0
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith("# ") or stripped.startswith("## ") or stripped.startswith("### ")) and len(stripped) < 120:
                sections.append(SystemPromptSection(
                    title=stripped,
                    content="",
                    start_offset=offset,
                    end_offset=offset + len(line),
                ))
            offset += len(line) + 1
        for i, section in enumerate(sections):
            next_start = sections[i + 1].start_offset if i + 1 < len(sections) else len(text)
            section.content = text[section.end_offset:next_start].strip()
            section.end_offset = next_start
        return sections

    def _extract_messages(self, messages: list[dict[str, Any]]) -> list[ParsedMessage]:
        parsed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                content = "\n".join(text_parts)
            tool_calls = None
            if msg.get("tool_use") or msg.get("type") == "tool_use":
                tool_calls = [msg]
            parsed.append(ParsedMessage(role=msg["role"], content=content, tool_calls=tool_calls))
        return parsed

    def _extract_tools(self, tools: list[dict[str, Any]]) -> list[ParsedTool]:
        return [
            ParsedTool(
                name=t.get("name", "unknown"),
                description=t.get("description", ""),
                parameters=t.get("input_schema"),
            )
            for t in tools
        ]
