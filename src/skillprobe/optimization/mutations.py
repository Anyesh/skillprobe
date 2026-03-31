from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutation:
    operator: str
    description: str
    addition: str


OPERATOR_DESCRIPTIONS = {
    "add_constraint": "Add stricter rules to enforce desired behavior",
    "add_negative_example": "Add explicit 'do NOT' examples",
    "restructure": "Move most-failed rules to the top for emphasis",
    "tighten_language": "Replace vague words with precise instructions",
    "remove_bloat": "Remove rules that always pass (100% pass rate) to save tokens",
    "add_counterexample": "Add correct vs incorrect output examples",
}


def suggest_mutations(skill_content: str, failures: list) -> list[Mutation]:
    from skillprobe.optimization.analyzer import FailurePattern

    mutations = []

    for f in failures:
        if not isinstance(f, FailurePattern):
            continue

        if f.assertion_type == "not_contains":
            mutations.append(Mutation(
                operator="add_negative_example",
                description=f"Skill fails to prevent '{f.assertion_value}' ({f.failure_rate:.0%} failure rate in '{f.test_name}')",
                addition=f"- Never include '{f.assertion_value}' in your output.",
            ))

        elif f.assertion_type == "regex":
            mutations.append(Mutation(
                operator="add_constraint",
                description=f"Pattern '{f.assertion_value}' not matched ({f.failure_rate:.0%} failure rate in '{f.test_name}')",
                addition=_regex_to_instruction(f.assertion_value),
            ))

        elif f.assertion_type == "contains":
            mutations.append(Mutation(
                operator="add_constraint",
                description=f"Response missing '{f.assertion_value}' ({f.failure_rate:.0%} failure rate in '{f.test_name}')",
                addition=f"- Always include '{f.assertion_value}' in your response when relevant.",
            ))

        elif f.assertion_type in ("skill_loaded", "skill_present"):
            continue

    seen = set()
    unique = []
    for m in mutations:
        if m.addition not in seen:
            seen.add(m.addition)
            unique.append(m)

    return unique


def apply_mutation(skill_path: Path, mutation: Mutation) -> str:
    content = skill_path.read_text(encoding="utf-8")

    backup_path = skill_path.with_suffix(".md.bak")
    backup_path.write_text(content, encoding="utf-8")

    lines = content.split("\n")
    insert_idx = len(lines)

    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                insert_idx = i + 1
                break

    new_lines = lines[:insert_idx] + [mutation.addition] + lines[insert_idx:]
    new_content = "\n".join(new_lines)
    skill_path.write_text(new_content, encoding="utf-8")
    return new_content


def revert_mutation(skill_path: Path) -> bool:
    backup_path = skill_path.with_suffix(".md.bak")
    if not backup_path.exists():
        return False
    content = backup_path.read_text(encoding="utf-8")
    skill_path.write_text(content, encoding="utf-8")
    backup_path.unlink()
    return True


def _regex_to_instruction(pattern: str) -> str:
    if "-> " in pattern:
        return "- Always include return type annotations on functions (e.g., -> int, -> str, -> None)."
    if r"def \w+\(" in pattern:
        return "- Always write proper function definitions."
    if r"\w+:" in pattern and "def" in pattern:
        return "- Always use type hints on function parameters."
    if "^import" in pattern or "^from" in pattern:
        return "- Always put import statements at the top of the file."
    return f"- Ensure output matches the pattern: {pattern}"
