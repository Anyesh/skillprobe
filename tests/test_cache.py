import pytest

from skillprobe.cache import RunCache, compute_cache_key
from skillprobe.evidence import StepEvidence, ToolCallEvent


@pytest.fixture
def sample_skill_dir(tmp_path):
    skill = tmp_path / "skills" / "sample"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: sample\ndescription: sample skill\n---\nRules."
    )
    return skill


@pytest.fixture
def sample_evidence():
    return StepEvidence(
        response_text="ok",
        tool_calls=[],
        session_id="sess-1",
        duration_ms=100.0,
        cost_usd=0.01,
        exit_code=0,
        is_error=False,
        raw_output='{"type":"result"}',
        capture_id=None,
    )


def test_compute_cache_key_is_deterministic(sample_skill_dir):
    k1 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="do the thing",
        model="claude-haiku-4-5-20251001",
        harness="claude-code",
        version="0.4.0",
    )
    k2 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="do the thing",
        model="claude-haiku-4-5-20251001",
        harness="claude-code",
        version="0.4.0",
    )
    assert k1 == k2
    assert len(k1) == 64


def test_compute_cache_key_changes_when_prompt_changes(sample_skill_dir):
    k1 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="prompt one",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    k2 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="prompt two",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    assert k1 != k2


def test_compute_cache_key_changes_when_skill_contents_change(sample_skill_dir):
    k1 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    (sample_skill_dir / "SKILL.md").write_text(
        "---\nname: sample\ndescription: different\n---\nRules."
    )
    k2 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    assert k1 != k2


def test_compute_cache_key_changes_with_harness(sample_skill_dir):
    k1 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    k2 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="cursor",
        version="0.4.0",
    )
    assert k1 != k2


def test_compute_cache_key_changes_with_version(sample_skill_dir):
    k1 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="claude-code",
        version="0.4.0",
    )
    k2 = compute_cache_key(
        skills=[sample_skill_dir],
        prompt="p",
        model="m",
        harness="claude-code",
        version="0.5.0",
    )
    assert k1 != k2


def test_compute_cache_key_with_empty_skills_is_still_deterministic():
    k1 = compute_cache_key(
        skills=[], prompt="p", model="m", harness="claude-code", version="0.4.0"
    )
    k2 = compute_cache_key(
        skills=[], prompt="p", model="m", harness="claude-code", version="0.4.0"
    )
    assert k1 == k2


class TestRunCache:
    def test_put_then_get_round_trips_evidence(self, tmp_path, sample_evidence):
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=24)
        key = "a" * 64
        cache.put(key, sample_evidence)
        got = cache.get(key)
        assert got is not None
        assert got.response_text == sample_evidence.response_text
        assert got.session_id == sample_evidence.session_id
        assert got.cost_usd == sample_evidence.cost_usd
        assert got.duration_ms == sample_evidence.duration_ms
        assert got.is_error == sample_evidence.is_error

    def test_get_missing_key_returns_none(self, tmp_path):
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=24)
        assert cache.get("b" * 64) is None

    def test_expired_entry_returns_none(self, tmp_path, sample_evidence):
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=0)
        key = "c" * 64
        cache.put(key, sample_evidence)
        assert cache.get(key) is None

    def test_cache_survives_across_instances(self, tmp_path, sample_evidence):
        cache_dir = tmp_path / "cache"
        cache1 = RunCache(cache_dir=cache_dir, ttl_hours=24)
        key = "d" * 64
        cache1.put(key, sample_evidence)
        cache2 = RunCache(cache_dir=cache_dir, ttl_hours=24)
        got = cache2.get(key)
        assert got is not None
        assert got.response_text == sample_evidence.response_text

    def test_disabled_cache_ignores_put_and_get(self, tmp_path, sample_evidence):
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=24, disabled=True)
        cache.put("e" * 64, sample_evidence)
        assert cache.get("e" * 64) is None

    def test_roundtrip_preserves_tool_calls(self, tmp_path):
        evidence = StepEvidence(
            response_text="used tools",
            tool_calls=[
                ToolCallEvent(
                    tool_name="Bash",
                    status="completed",
                    arguments={"command": "ls"},
                ),
                ToolCallEvent(
                    tool_name="Skill",
                    status="completed",
                    arguments={"skill": "commit"},
                ),
            ],
            session_id="sess-2",
            duration_ms=500.0,
            cost_usd=0.02,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=24)
        cache.put("f" * 64, evidence)
        got = cache.get("f" * 64)
        assert got is not None
        assert len(got.tool_calls) == 2
        assert got.tool_calls[0].tool_name == "Bash"
        assert got.tool_calls[0].arguments == {"command": "ls"}
        assert got.tool_calls[1].tool_name == "Skill"
        assert got.tool_calls[1].arguments == {"skill": "commit"}

    def test_corrupt_utf8_entry_returns_none(self, tmp_path):
        cache = RunCache(cache_dir=tmp_path / "cache", ttl_hours=24)
        key = "g" * 64
        path = cache._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfe not valid utf-8")
        assert cache.get(key) is None
