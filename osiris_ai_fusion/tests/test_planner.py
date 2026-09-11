import pytest

from graph import _plan_tools


def test_planner_selects_keyword_tools():
    tools = _plan_tools("İzmir deprem ve yangın durumunu araştır")
    assert "earthquakes" in tools
    assert "fires" in tools


def test_planner_rejects_unknown_requested_tool():
    with pytest.raises(PermissionError):
        _plan_tools("test", ["active_scanner"])
