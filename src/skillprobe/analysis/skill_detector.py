from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoadedSkill:
    name: str
    path: Path
    content: str
    description: str


@dataclass
class SkillMatch:
    name: str
    path: Path
    score: float
    matched_lines: list[str]


class SkillDetector:
    def __init__(self, skill_dirs: list[Path]):
        self.skills: list[LoadedSkill] = []
        for d in skill_dirs:
            self._load_directory(d)

    def _load_directory(self, directory: Path):
        if not directory.exists():
            return
        for path in directory.rglob("*.md"):
            content = path.read_text(encoding="utf-8", errors="replace")
            description = self._extract_description(content)
            body = self._strip_frontmatter(content)
            self.skills.append(LoadedSkill(
                name=path.name,
                path=path,
                content=body,
                description=description,
            ))

    def _extract_description(self, content: str) -> str:
        if not content.startswith("---"):
            return ""
        lines = content.split("\n")
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.strip().startswith("description:"):
                return line.split(":", 1)[1].strip().strip("\"'")
        return ""

    def _strip_frontmatter(self, content: str) -> str:
        if not content.startswith("---"):
            return content
        lines = content.split("\n")
        end_idx = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx == -1:
            return content
        return "\n".join(lines[end_idx + 1:]).strip()

    def _line_matches_prompt(self, line: str, prompt_lower: str) -> bool:
        line_lower = line.lower()
        if line_lower in prompt_lower or prompt_lower in line_lower:
            return True
        words = [w for w in line_lower.split() if len(w) > 3]
        if not words:
            return False
        hits = sum(1 for w in words if w in prompt_lower)
        return hits / len(words) >= 0.6

    def detect(self, system_prompt: str) -> list[SkillMatch]:
        matches = []
        prompt_lower = system_prompt.lower()
        for skill in self.skills:
            skill_lines = [
                line.strip() for line in skill.content.split("\n")
                if line.strip() and len(line.strip()) > 10
            ]
            if not skill_lines:
                continue
            matched = [
                line for line in skill_lines
                if self._line_matches_prompt(line, prompt_lower)
            ]
            if not matched:
                continue
            score = len(matched) / len(skill_lines)
            if score >= 0.3:
                matches.append(SkillMatch(
                    name=skill.name,
                    path=skill.path,
                    score=score,
                    matched_lines=matched,
                ))
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches
