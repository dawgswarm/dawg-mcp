import pytest

from dawg_mcp.config import Config
from dawg_mcp.session import SessionManager, parse_geo
from conftest import FakeSession


def test_parse_geo_none():
    assert parse_geo(None) is None
    assert parse_geo("") is None


def test_parse_geo_slug():
    assert parse_geo("moskva") == "moskva"


def test_parse_geo_coords():
    assert parse_geo("55.75,37.61") == (55.75, 37.61)


def test_parse_geo_bad_coords_falls_back_to_slug():
    # Not two floats -> treated as a slug string.
    assert parse_geo("a,b") == "a,b"


def _mgr() -> SessionManager:
    return SessionManager(Config(api_key="k"), pw=None)


def test_get_no_sessions_raises():
    with pytest.raises(KeyError):
        _mgr().get(None)


def test_get_single_session_default():
    mgr = _mgr()
    s = FakeSession("only")
    mgr._sessions["only"] = s
    assert mgr.get(None) is s


def test_get_ambiguous_requires_id():
    mgr = _mgr()
    mgr._sessions["a"] = FakeSession("a")
    mgr._sessions["b"] = FakeSession("b")
    with pytest.raises(KeyError):
        mgr.get(None)
    assert mgr.get("b").session_id == "b"


def test_get_unknown_id_raises():
    mgr = _mgr()
    mgr._sessions["a"] = FakeSession("a")
    with pytest.raises(KeyError):
        mgr.get("missing")
