"""Cover recursive subquery planning and the limits that keep it safe."""

from __future__ import annotations

import pytest

from config import get_settings
from subquery import (
    allocate_subquery_calls,
    plan_subqueries,
    split_deterministic,
)


@pytest.fixture(autouse=True)
def deterministic_only(monkeypatch):
    """Keep the planner model out of it; the model path is covered separately."""
    monkeypatch.setenv("AI_PLANNER_ENABLED", "false")
    monkeypatch.setenv("SUBQUERY_PLANNING_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestDeterministicSplit:
    def test_splits_on_strong_boundaries(self):
        parts = split_deterministic(
            "İzmir'de son 24 saatte deprem oldu mu? Ege'de orman yangını var mı?"
        )
        assert len(parts) == 2
        assert parts[0].startswith("İzmir")
        assert parts[1].startswith("Ege")

    def test_semicolons_and_newlines_are_boundaries(self):
        assert len(split_deterministic("earthquake risk in Izmir; wildfire risk in Mugla")) == 2
        assert len(split_deterministic("earthquake risk in Izmir\nwildfire risk in Mugla")) == 2

    def test_an_atomic_question_is_not_split(self):
        assert split_deterministic("İzmir'de bugün hava nasıl") == []

    def test_a_fragment_that_cannot_stand_alone_blocks_the_split(self):
        # "İzmir" on its own has lost the predicate; researching it is worse than
        # not recursing, so the whole split is refused rather than half-taken.
        assert split_deterministic("İzmir? Ege bölgesinde deprem riski nedir") == []

    def test_conjunctions_alone_are_not_boundaries(self):
        # "ve" joins a single predicate far more often than it joins two questions.
        assert split_deterministic("İzmir ve Ege bölgesinde deprem riski") == []


class TestPlanSubqueries:
    async def test_disabled_planning_returns_nothing(self, monkeypatch):
        monkeypatch.setenv("SUBQUERY_PLANNING_ENABLED", "false")
        get_settings.cache_clear()
        assert await plan_subqueries("a? b? c?") == []

    async def test_fast_path_never_calls_model_splitter(self, monkeypatch):
        monkeypatch.setenv("AI_PLANNER_ENABLED", "true")
        get_settings.cache_clear()

        async def forbidden(*args, **kwargs):
            raise AssertionError("slow model must not run on the fast path")

        monkeypatch.setattr("subquery._split_with_model", forbidden)
        assert await plan_subqueries(
            "İzmir'de bugün hava nasıl",
            allow_model=False,
        ) == []

    async def test_fast_path_keeps_safe_deterministic_decomposition(self):
        planned = await plan_subqueries(
            "İzmir'de deprem riski nedir? Muğla'da yangın riski nedir?",
            allow_model=False,
        )
        assert planned
        assert all(item.origin == "deterministic" for item in planned)

    async def test_subqueries_are_derived_from_a_compound_question(self):
        planned = await plan_subqueries(
            "İzmir'de deprem riski nedir? Muğla'da orman yangını riski nedir?"
        )
        assert [item.depth for item in planned] == [1, 1]
        assert all(item.origin == "deterministic" for item in planned)

    async def test_the_root_question_never_becomes_its_own_subquery(self):
        root = "İzmir'de deprem riski nedir? Muğla'da yangın riski nedir?"
        assert all(item.query != root for item in await plan_subqueries(root))

    async def test_the_count_cap_is_honoured(self, monkeypatch):
        monkeypatch.setenv("SUBQUERY_MAX_COUNT", "2")
        get_settings.cache_clear()
        planned = await plan_subqueries(
            "birinci soru nedir? ikinci soru nedir? üçüncü soru nedir? dördüncü soru nedir?"
        )
        assert len(planned) == 2

    async def test_recursion_stops_at_the_depth_cap(self, monkeypatch):
        monkeypatch.setenv("SUBQUERY_MAX_DEPTH", "1")
        monkeypatch.setenv("SUBQUERY_MAX_COUNT", "8")
        get_settings.cache_clear()
        planned = await plan_subqueries(
            "ilk konu hakkında ne biliniyor? ikinci konu hakkında ne biliniyor?"
        )
        assert planned
        assert {item.depth for item in planned} == {1}

    async def test_deeper_questions_are_reached_when_depth_allows(self, monkeypatch):
        monkeypatch.setenv("SUBQUERY_MAX_DEPTH", "2")
        monkeypatch.setenv("SUBQUERY_MAX_COUNT", "8")
        get_settings.cache_clear()
        # The first level splits on "?", and each half still contains a ";".
        planned = await plan_subqueries(
            "deprem riski nedir; yangın riski nedir? "
            "sel riski nedir; fırtına riski nedir?"
        )
        depths = {item.depth for item in planned}
        assert 1 in depths and 2 in depths

    async def test_identical_branches_are_not_researched_twice(self):
        planned = await plan_subqueries("aynı soru nedir? aynı soru nedir?")
        assert len({item.query for item in planned}) == len(planned)


class TestBudgetAndAuthority:
    def test_subqueries_never_reach_an_unauthorized_tool(self):
        calls = allocate_subquery_calls(
            planned_tools=["provider_federation"],
            # A caller passing a tool the plan never sealed must not widen authority.
            research_tools=["provider_federation", "never_authorized"],
            subqueries=["q1", "q2"],
            max_tool_calls=8,
        )
        assert {tool for tool, _ in calls} == {"provider_federation"}

    def test_total_calls_never_exceed_the_root_budget(self):
        planned = ["provider_federation"]
        calls = allocate_subquery_calls(
            planned_tools=planned,
            research_tools=planned,
            subqueries=[f"q{i}" for i in range(20)],
            max_tool_calls=4,
        )
        assert len(planned) + len(calls) <= 4

    def test_a_root_plan_that_spent_the_budget_gets_no_subqueries(self):
        planned = ["a", "b", "c", "d"]
        assert allocate_subquery_calls(
            planned_tools=planned,
            research_tools=planned,
            subqueries=["q1"],
            max_tool_calls=4,
        ) == []

    def test_no_research_capable_tool_means_no_fan_out(self):
        # Feeds return the same payload whatever is asked, so re-running them under
        # a subquery would duplicate one payload and fake corroboration.
        assert allocate_subquery_calls(
            planned_tools=["earthquakes", "fires"],
            research_tools=[],
            subqueries=["q1", "q2"],
            max_tool_calls=8,
        ) == []

    def test_shallow_questions_survive_a_budget_that_runs_out(self):
        calls = allocate_subquery_calls(
            planned_tools=["provider_federation"],
            research_tools=["provider_federation"],
            subqueries=["shallow", "deeper", "deepest"],
            max_tool_calls=3,
        )
        assert [question for _, question in calls] == ["shallow", "deeper"]


class TestResearchTools:
    def test_only_query_sensitive_capabilities_are_fanned_out(self):
        from capabilities import is_research_tool

        # Re-running a feed under a different question returns the same payload,
        # so it would duplicate evidence and fake corroboration.
        assert is_research_tool("earthquakes") is False
        assert is_research_tool("fires") is False
        # Local kinds reason from the model instead of fetching evidence.
        assert is_research_tool("calculator") is False
        assert is_research_tool("direct_reasoning") is False
        # External research is the one kind worth asking a second question.
        assert is_research_tool("provider_federation") is True
        assert is_research_tool("no_such_tool") is False
