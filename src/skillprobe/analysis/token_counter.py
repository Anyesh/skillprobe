from dataclasses import dataclass

import tiktoken

from skillprobe.parsers.base import SystemPromptSection


@dataclass
class TokenCount:
    total: int
    text_length: int


@dataclass
class SectionTokenCount:
    section_title: str
    tokens: int
    text_length: int
    percentage: float


class TokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base"):
        self._enc = tiktoken.get_encoding(encoding_name)

    def count_text(self, text: str) -> int:
        return len(self._enc.encode(text))

    def count_system(self, text: str) -> TokenCount:
        return TokenCount(total=self.count_text(text), text_length=len(text))

    def count_sections(self, sections: list[SystemPromptSection]) -> list[SectionTokenCount]:
        counts = []
        total = 0
        for s in sections:
            full_text = f"{s.title}\n{s.content}"
            tokens = self.count_text(full_text)
            total += tokens
            counts.append(SectionTokenCount(
                section_title=s.title,
                tokens=tokens,
                text_length=len(full_text),
                percentage=0.0,
            ))
        if total > 0:
            for c in counts:
                c.percentage = c.tokens / total
        return counts
