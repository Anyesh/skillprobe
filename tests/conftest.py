import pytest

from skillprobe.config import ProxyConfig


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def config(tmp_db):
    return ProxyConfig(db_path=tmp_db)
