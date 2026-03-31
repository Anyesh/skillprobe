from skillprobe.parsers.anthropic import AnthropicParser


class TestAnthropicParserCanParse:
    def test_matches_messages_path(self):
        parser = AnthropicParser()
        assert parser.can_parse("/v1/messages", {}) is True

    def test_rejects_other_paths(self):
        parser = AnthropicParser()
        assert parser.can_parse("/v1/chat/completions", {}) is False

    def test_matches_with_query_params(self):
        parser = AnthropicParser()
        assert parser.can_parse("/v1/messages?beta=true", {}) is True


class TestAnthropicParserStringSystem:
    def test_parses_string_system_prompt(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "max_tokens": 1024,
            "system": "You are a helpful assistant.\n\n# Skills\n## Skill: test\nDo testing.",
            "messages": [{"role": "user", "content": "hello"}],
        }
        result = parser.parse(body)
        assert result.provider == "anthropic"
        assert result.model == "claude-sonnet-4-6-20250514"
        assert "helpful assistant" in result.system_prompt
        assert result.max_tokens == 1024
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert result.messages[0].content == "hello"

    def test_detects_sections_in_string_system(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "system": "Preamble.\n\n# Section One\nContent one.\n\n## Subsection\nContent two.\n\n# Section Two\nMore.",
            "messages": [],
        }
        result = parser.parse(body)
        titles = [s.title for s in result.system_sections]
        assert "# Section One" in titles
        assert "## Subsection" in titles
        assert "# Section Two" in titles


class TestAnthropicParserBlockSystem:
    def test_parses_array_system_blocks(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-opus-4-6-20250514",
            "system": [
                {"type": "text", "text": "Block one content."},
                {"type": "text", "text": "# Skills\n## Skill: review\nReview code.", "cache_control": {"type": "ephemeral"}},
            ],
            "messages": [{"role": "user", "content": "hi"}],
        }
        result = parser.parse(body)
        assert "Block one content." in result.system_prompt
        assert "Review code." in result.system_prompt
        assert len(result.system_sections) >= 1


class TestAnthropicParserTools:
    def test_parses_tool_definitions(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "system": "You are helpful.",
            "messages": [],
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file from disk",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
                {
                    "name": "run_test",
                    "description": "Run tests",
                    "input_schema": {"type": "object", "properties": {}},
                },
            ],
        }
        result = parser.parse(body)
        assert len(result.tools) == 2
        assert result.tools[0].name == "read_file"
        assert result.tools[0].description == "Read a file from disk"
        assert result.tools[1].name == "run_test"


class TestAnthropicParserEdgeCases:
    def test_no_system_prompt(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "hello"}],
        }
        result = parser.parse(body)
        assert result.system_prompt == ""
        assert result.system_sections == []

    def test_stream_flag(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "system": "test",
            "messages": [],
            "stream": True,
        }
        result = parser.parse(body)
        assert result.stream is True

    def test_complex_message_content(self):
        parser = AnthropicParser()
        body = {
            "model": "claude-sonnet-4-6-20250514",
            "system": "test",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Look at this code:"},
                        {"type": "text", "text": "def foo(): pass"},
                    ],
                }
            ],
        }
        result = parser.parse(body)
        assert "Look at this code:" in result.messages[0].content
        assert "def foo(): pass" in result.messages[0].content
