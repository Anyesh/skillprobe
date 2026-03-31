from typing import Any

from skillprobe.parsers.base import (
    ParsedMessage,
    ParsedRequest,
    ParsedTool,
    SystemPromptSection,
)

SYSTEM_ROLES = {"system", "developer"}


class OpenAIParser:
    def can_parse(self, path: str, body: dict[str, Any]) -> bool:
        return path.split("?")[0].rstrip("/") == "/v1/chat/completions"

    def parse(self, body: dict[str, Any]) -> ParsedRequest:
        messages = body.get("messages", [])
        system_parts, non_system = self._split_messages(messages)
        system_prompt = "\n\n".join(system_parts)
        return ParsedRequest(
            provider="openai",
            model=body.get("model", "unknown"),
            system_prompt=system_prompt,
            system_sections=self._extract_sections(system_prompt),
            messages=non_system,
            tools=self._extract_tools(body.get("tools", [])),
            max_tokens=body.get("max_tokens") or body.get("max_completion_tokens"),
            temperature=body.get("temperature"),
            stream=body.get("stream", False),
            raw_system=system_parts,
        )

    def _split_messages(self, messages: list[dict[str, Any]]) -> tuple[list[str], list[ParsedMessage]]:
        system_parts = []
        non_system = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                content = "\n".join(text_parts)
            if role in SYSTEM_ROLES:
                system_parts.append(content)
            else:
                tool_calls = msg.get("tool_calls")
                non_system.append(ParsedMessage(role=role, content=content, tool_calls=tool_calls))
        return system_parts, non_system

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

    def _extract_tools(self, tools: list[dict[str, Any]]) -> list[ParsedTool]:
        parsed = []
        for t in tools:
            if t.get("type") == "function":
                func = t.get("function", {})
                parsed.append(ParsedTool(
                    name=func.get("name", "unknown"),
                    description=func.get("description", ""),
                    parameters=func.get("parameters"),
                ))
            else:
                parsed.append(ParsedTool(
                    name=t.get("name", "unknown"),
                    description=t.get("description", ""),
                    parameters=t.get("parameters"),
                ))
        return parsed
