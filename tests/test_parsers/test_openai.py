from skillprobe.parsers.openai import OpenAIParser


class TestOpenAIParserCanParse:
    def test_matches_chat_completions(self):
        parser = OpenAIParser()
        assert parser.can_parse("/v1/chat/completions", {}) is True

    def test_rejects_other_paths(self):
        parser = OpenAIParser()
        assert parser.can_parse("/v1/messages", {}) is False


class TestOpenAIParserSystem:
    def test_extracts_system_from_messages(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are helpful.\n\n# Skills\n## Code Review\nReview code."},
                {"role": "user", "content": "hello"},
            ],
        }
        result = parser.parse(body)
        assert result.provider == "openai"
        assert result.model == "gpt-4o"
        assert "You are helpful." in result.system_prompt
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"

    def test_multiple_system_messages(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Part one."},
                {"role": "system", "content": "Part two."},
                {"role": "user", "content": "hi"},
            ],
        }
        result = parser.parse(body)
        assert "Part one." in result.system_prompt
        assert "Part two." in result.system_prompt

    def test_developer_role_as_system(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [
                {"role": "developer", "content": "Instructions here."},
                {"role": "user", "content": "hi"},
            ],
        }
        result = parser.parse(body)
        assert "Instructions here." in result.system_prompt


class TestOpenAIParserTools:
    def test_parses_function_tools(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather",
                        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                    },
                }
            ],
        }
        result = parser.parse(body)
        assert len(result.tools) == 1
        assert result.tools[0].name == "get_weather"


class TestOpenAIParserEdgeCases:
    def test_no_system_message(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        }
        result = parser.parse(body)
        assert result.system_prompt == ""

    def test_stream_flag(self):
        parser = OpenAIParser()
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
        result = parser.parse(body)
        assert result.stream is True
