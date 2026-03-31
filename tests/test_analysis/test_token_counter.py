from skillprobe.analysis.token_counter import TokenCounter
from skillprobe.parsers.base import SystemPromptSection


class TestTokenCounter:
    def test_counts_total_system_tokens(self):
        counter = TokenCounter()
        result = counter.count_system("You are a helpful assistant. Please help the user.")
        assert result.total > 0

    def test_longer_text_has_more_tokens(self):
        counter = TokenCounter()
        short = counter.count_system("Hello.")
        long = counter.count_system("Hello. " * 100)
        assert long.total > short.total

    def test_counts_per_section(self):
        counter = TokenCounter()
        sections = [
            SystemPromptSection("# Skills", "Skill content here with many words.", 0, 50),
            SystemPromptSection("# Rules", "Rule content.", 50, 70),
        ]
        result = counter.count_sections(sections)
        assert len(result) == 2
        assert result[0].section_title == "# Skills"
        assert result[0].tokens > 0
        assert result[1].section_title == "# Rules"


class TestTokenCounterReport:
    def test_format_breakdown(self):
        counter = TokenCounter()
        sections = [
            SystemPromptSection("# Skills", "Lots of skill content " * 20, 0, 100),
            SystemPromptSection("# Config", "Short.", 100, 110),
        ]
        breakdown = counter.count_sections(sections)
        assert breakdown[0].tokens > breakdown[1].tokens
