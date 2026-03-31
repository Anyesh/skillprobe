from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 9339
    anthropic_api_url: str = "https://api.anthropic.com"
    openai_api_url: str = "https://api.openai.com"
    db_path: Path = field(default_factory=lambda: Path("skillprobe.db"))
    skill_dirs: list[Path] = field(default_factory=list)
    capture_responses: bool = True
    watch_test_file: Path | None = None
    session: str | None = None
