from pathlib import Path

import pytest
import yaml

from skillprobe.activation import load_activation_suite
from skillprobe.loader import load_scenario_suite

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "tests"


def _example_yaml_files() -> list[Path]:
    return sorted(EXAMPLES_DIR.rglob("*.yaml"))


def _is_activation_file(path: Path) -> bool:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return isinstance(data, dict) and "activation" in data and "scenarios" not in data


@pytest.mark.parametrize(
    "yaml_path", _example_yaml_files(), ids=lambda p: str(p.relative_to(EXAMPLES_DIR))
)
def test_every_shipped_example_parses_with_correct_loader(yaml_path: Path) -> None:
    if _is_activation_file(yaml_path):
        load_activation_suite(yaml_path)
    else:
        load_scenario_suite(yaml_path)
