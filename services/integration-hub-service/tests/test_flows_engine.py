"""Pure tests for app/flows/engine.py -- no database, no fixtures.

`FlowEngine` takes its `executor`/`sleep` collaborators by injection, so
every test here supplies its own real (never mocked) async callables: a
recording executor that runs actual Python and returns/raises for real,
and -- for the retry/backoff tests specifically -- a fake `sleep` that
records its calls and returns instantly rather than actually waiting out
`shared_core.queue.retry.compute_backoff_delay`'s own real seconds.

Note that only steps the top-level `run()` loop visits directly are ever
appended to `FlowRunResult.steps_executed` -- a `loop`/`parallel` step's
own *body* steps are not (they run through the private `_run_body` nested
sub-sequence instead), so tests confirming loop/parallel body execution
assert on the recording executor's own call log, not on `steps_executed`.
"""

from __future__ import annotations

import time

import pytest

from app.flows.engine import FlowEngine, FlowRunResult

ActionLog = list[str]


def _make_recording_executor(log: ActionLog, *, fail_on: set[str] | None = None):
    """A real `StepExecutor` that records every action name it was called with."""

    async def _executor(action, config, context):
        log.append(action)
        if fail_on and action in fail_on:
            raise RuntimeError(f"{action} failed")
        return {}

    return _executor


async def _noop_sleep(seconds: float) -> None:
    return None


class TestSequentialActionChain:
    async def test_runs_every_action_step_in_order(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "s1",
            "steps": {
                "s1": {"kind": "action", "action": "first", "next": "s2"},
                "s2": {"kind": "action", "action": "second", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.status == "succeeded"
        assert log == ["first", "second"]
        assert result.steps_executed == ["s1", "s2"]

    async def test_an_action_steps_own_result_is_merged_into_the_context(self) -> None:
        async def executor(action, config, context):
            return {"order_id": "abc-123"}

        definition = {"start": "s1", "steps": {"s1": {"kind": "action", "action": "create", "next": None}}}
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition)
        assert result.context["order_id"] == "abc-123"

    async def test_a_step_with_no_explicit_kind_defaults_to_action(self) -> None:
        log: ActionLog = []
        definition = {"start": "s1", "steps": {"s1": {"action": "implicit", "next": None}}}
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.status == "succeeded"
        assert log == ["implicit"]

    async def test_a_terminal_next_of_none_stops_the_run(self) -> None:
        log: ActionLog = []
        definition = {"start": "s1", "steps": {"s1": {"kind": "action", "action": "only", "next": None}}}
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.steps_executed == ["s1"]

    async def test_an_initial_context_is_preserved_and_extended(self) -> None:
        async def executor(action, config, context):
            return {"added": True}

        definition = {"start": "s1", "steps": {"s1": {"kind": "action", "action": "a", "next": None}}}
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition, context={"seed": "value"})
        assert result.context == {"seed": "value", "added": True}


class TestConditionBranching:
    def _definition(self, operator: str = "gt", value: object = 50) -> dict:
        return {
            "start": "cond",
            "steps": {
                "cond": {
                    "kind": "condition",
                    "rule": {"field": "score", "operator": operator, "value": value},
                    "then": "pass_step",
                    "else": "fail_step",
                },
                "pass_step": {"kind": "action", "action": "mark_pass", "next": None},
                "fail_step": {"kind": "action", "action": "mark_fail", "next": None},
            },
        }

    async def test_takes_the_then_branch_when_the_rule_matches(self) -> None:
        log: ActionLog = []
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(self._definition(), context={"score": 80})
        assert log == ["mark_pass"]
        assert result.steps_executed == ["cond", "pass_step"]

    async def test_takes_the_else_branch_when_the_rule_mismatches(self) -> None:
        log: ActionLog = []
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(self._definition(), context={"score": 10})
        assert log == ["mark_fail"]
        assert result.steps_executed == ["cond", "fail_step"]

    async def test_resolves_a_dotted_field_path_from_the_context(self) -> None:
        log: ActionLog = []
        definition = self._definition("eq", "us")
        definition["steps"]["cond"]["rule"] = {"field": "meta.region", "operator": "eq", "value": "us"}
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition, context={"meta": {"region": "us"}})
        assert log == ["mark_pass"]

    async def test_a_missing_context_field_takes_the_else_branch(self) -> None:
        log: ActionLog = []
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(self._definition(), context={})
        assert log == ["mark_fail"]

    async def test_an_unrecognised_condition_operator_takes_the_else_branch_rather_than_raising(
        self,
    ) -> None:
        # Unlike the transformations engine's own `evaluate_rule`, a flow condition never
        # raises on a bad operator -- `_CONDITION_COMPARATORS.get(...)` simply misses and
        # the step evaluates to False, so this engine keeps traversing rather than aborting
        # a whole run over one malformed rule.
        log: ActionLog = []
        definition = self._definition("bogus", 1)
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition, context={"score": 1})
        assert log == ["mark_fail"]


class TestLoop:
    async def test_runs_the_body_once_per_item_setting_loop_item_and_index(self) -> None:
        recorded: list[tuple[object, int]] = []

        async def executor(action, config, context):
            if action == "record":
                recorded.append((context["_loop_item"], context["_loop_index"]))
            return {}

        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {"kind": "loop", "over": "items", "body": "record_item", "next": None},
                "record_item": {"kind": "action", "action": "record", "next": None},
            },
        }
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition, context={"items": ["a", "b", "c"]})
        assert result.status == "succeeded"
        assert recorded == [("a", 0), ("b", 1), ("c", 2)]

    async def test_max_iterations_bounds_the_number_of_body_runs(self) -> None:
        recorded: list[object] = []

        async def executor(action, config, context):
            if action == "record":
                recorded.append(context["_loop_item"])
            return {}

        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {
                    "kind": "loop",
                    "over": "items",
                    "body": "record_item",
                    "max_iterations": 2,
                    "next": None,
                },
                "record_item": {"kind": "action", "action": "record", "next": None},
            },
        }
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition, context={"items": ["a", "b", "c", "d"]})
        assert result.status == "succeeded"
        assert recorded == ["a", "b"]

    async def test_a_multi_step_body_chain_runs_in_full_each_iteration(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {"kind": "loop", "over": "items", "body": "b1", "next": None},
                "b1": {"kind": "action", "action": "b1_action", "next": "b2"},
                "b2": {"kind": "action", "action": "b2_action", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        await engine.run(definition, context={"items": [1, 2]})
        assert log == ["b1_action", "b2_action", "b1_action", "b2_action"]

    async def test_body_steps_are_not_recorded_in_the_top_level_steps_executed_list(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {"kind": "loop", "over": "items", "body": "record_item", "next": None},
                "record_item": {"kind": "action", "action": "record", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition, context={"items": ["a", "b"]})
        assert result.steps_executed == ["loop1"]

    async def test_an_empty_iterable_runs_the_body_zero_times(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {"kind": "loop", "over": "items", "body": "record_item", "next": None},
                "record_item": {"kind": "action", "action": "record", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition, context={"items": []})
        assert log == []
        assert result.status == "succeeded"

    async def test_an_approval_step_inside_a_loop_body_fails_the_run(self) -> None:
        # `_run_body` explicitly refuses approval gating inside a loop/parallel body --
        # confirmed directly against `app/flows/engine.py`'s own `_run_body`.
        async def executor(action, config, context):
            return {}

        definition = {
            "start": "loop1",
            "steps": {
                "loop1": {"kind": "loop", "over": "items", "body": "appr", "next": None},
                "appr": {"kind": "approval", "next": None},
            },
        }
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition, context={"items": ["a"]})
        assert result.status == "failed"
        assert result.error == "Approval steps are not supported inside a loop/parallel body."

    async def test_an_unknown_body_step_id_fails_the_run(self) -> None:
        async def executor(action, config, context):
            return {}

        definition = {
            "start": "loop1",
            "steps": {"loop1": {"kind": "loop", "over": "items", "body": "ghost", "next": None}},
        }
        engine = FlowEngine(executor=executor)
        result = await engine.run(definition, context={"items": ["a"]})
        assert result.status == "failed"
        assert "ghost" in result.error


class TestParallel:
    async def test_runs_every_branch(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "par1",
            "steps": {
                "par1": {"kind": "parallel", "branches": ["b1", "b2"], "next": None},
                "b1": {"kind": "action", "action": "branch_one", "next": None},
                "b2": {"kind": "action", "action": "branch_two", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.status == "succeeded"
        assert set(log) == {"branch_one", "branch_two"}
        assert len(log) == 2

    async def test_each_branch_can_be_its_own_multi_step_chain(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "par1",
            "steps": {
                "par1": {"kind": "parallel", "branches": ["b1"], "next": None},
                "b1": {"kind": "action", "action": "b1_first", "next": "b1_second_step"},
                "b1_second_step": {"kind": "action", "action": "b1_second", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        await engine.run(definition)
        assert log == ["b1_first", "b1_second"]

    async def test_branch_steps_are_not_recorded_in_the_top_level_steps_executed_list(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "par1",
            "steps": {
                "par1": {"kind": "parallel", "branches": ["b1", "b2"], "next": None},
                "b1": {"kind": "action", "action": "branch_one", "next": None},
                "b2": {"kind": "action", "action": "branch_two", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.steps_executed == ["par1"]

    async def test_continues_to_the_parallel_steps_own_next_once_every_branch_completes(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "par1",
            "steps": {
                "par1": {"kind": "parallel", "branches": ["b1"], "next": "after"},
                "b1": {"kind": "action", "action": "branch_one", "next": None},
                "after": {"kind": "action", "action": "after_parallel", "next": None},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert log == ["branch_one", "after_parallel"]
        assert result.steps_executed == ["par1", "after"]


class TestApprovalGating:
    _definition = {
        "start": "appr",
        "steps": {
            "appr": {"kind": "approval", "next": "after"},
            "after": {"kind": "action", "action": "post_approval", "next": None},
        },
    }

    async def test_a_fresh_run_stops_awaiting_approval(self) -> None:
        log: ActionLog = []
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(self._definition)
        assert result.status == "awaiting_approval"
        assert result.awaiting_step == "appr"
        assert result.steps_executed == ["appr"]
        assert log == []

    async def test_resuming_with_the_approval_flag_set_completes_the_run(self) -> None:
        log: ActionLog = []
        engine = FlowEngine(executor=_make_recording_executor(log))
        first = await engine.run(self._definition)
        second = await engine.run(
            self._definition, context={f"_approved_{first.awaiting_step}": True}
        )
        assert second.status == "succeeded"
        assert second.steps_executed == ["appr", "after"]
        assert log == ["post_approval"]

    async def test_a_differently_named_approval_flag_does_not_satisfy_the_gate(self) -> None:
        engine = FlowEngine(executor=_make_recording_executor([]))
        result = await engine.run(self._definition, context={"_approved_someone_else": True})
        assert result.status == "awaiting_approval"


class TestRetryWithBackoff:
    async def test_succeeds_after_failing_fewer_times_than_max_attempts(self) -> None:
        calls: list[str] = []

        async def executor(action, config, context):
            calls.append(action)
            if len(calls) < 3:
                raise RuntimeError("transient failure")
            return {"outcome": "ok"}

        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "flaky", "max_attempts": 3, "next": None}},
        }
        engine = FlowEngine(executor=executor, sleep=fake_sleep)
        result = await engine.run(definition)
        assert result.status == "succeeded"
        assert len(calls) == 3
        assert result.context["outcome"] == "ok"
        assert len(sleeps) == 2

    async def test_never_sleeps_when_the_first_attempt_succeeds(self) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        async def executor(action, config, context):
            return {}

        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "a", "max_attempts": 5, "next": None}},
        }
        engine = FlowEngine(executor=executor, sleep=fake_sleep)
        await engine.run(definition)
        assert sleeps == []

    async def test_exhausting_every_attempt_still_sleeps_between_but_not_after_the_last(self) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        async def executor(action, config, context):
            raise RuntimeError("always fails")

        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "a", "max_attempts": 3, "next": None}},
        }
        engine = FlowEngine(executor=executor, sleep=fake_sleep)
        result = await engine.run(definition)
        assert result.status == "failed"
        assert len(sleeps) == 2

    async def test_defaults_to_a_single_attempt_when_max_attempts_is_omitted(self) -> None:
        calls: list[str] = []

        async def executor(action, config, context):
            calls.append(action)
            raise RuntimeError("nope")

        definition = {"start": "s1", "steps": {"s1": {"kind": "action", "action": "a", "next": None}}}
        engine = FlowEngine(executor=executor, sleep=_noop_sleep)
        result = await engine.run(definition)
        assert result.status == "failed"
        assert len(calls) == 1

    async def test_the_default_sleep_is_asyncio_sleep_when_none_is_injected(self) -> None:
        import asyncio

        engine = FlowEngine(executor=_make_recording_executor([]))
        assert engine._sleep is asyncio.sleep


class TestOnErrorCompensation:
    async def test_jumps_to_the_compensation_step_instead_of_failing_outright(self) -> None:
        log: ActionLog = []

        async def executor(action, config, context):
            log.append(action)
            if action == "always_fails":
                raise RuntimeError("bad thing happened")
            return {}

        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "always_fails",
                    "max_attempts": 1,
                    "next": "s2",
                    "on_error": "comp",
                },
                "s2": {"kind": "action", "action": "never_reached", "next": None},
                "comp": {"kind": "compensation", "action": "rollback", "next": None},
            },
        }
        engine = FlowEngine(executor=executor, sleep=_noop_sleep)
        result = await engine.run(definition)
        assert result.status == "succeeded"
        assert result.steps_executed == ["s1", "comp"]
        assert log == ["always_fails", "rollback"]
        assert "never_reached" not in log

    async def test_records_the_triggering_error_on_the_context(self) -> None:
        async def executor(action, config, context):
            if action == "always_fails":
                raise RuntimeError("specific failure message")
            return {}

        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "always_fails",
                    "max_attempts": 1,
                    "next": None,
                    "on_error": "comp",
                },
                "comp": {"kind": "compensation", "action": "rollback", "next": None},
            },
        }
        engine = FlowEngine(executor=executor, sleep=_noop_sleep)
        result = await engine.run(definition)
        assert result.context["last_error"] == "specific failure message"


class TestOutrightFailure:
    async def test_fails_with_no_on_error_configured(self) -> None:
        async def executor(action, config, context):
            raise RuntimeError("unrecoverable")

        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "a", "max_attempts": 1, "next": None}},
        }
        engine = FlowEngine(executor=executor, sleep=_noop_sleep)
        result = await engine.run(definition)
        assert result.status == "failed"
        assert result.error == "unrecoverable"
        assert result.steps_executed == ["s1"]


class TestUnknownStep:
    async def test_an_unknown_start_step_fails_cleanly(self) -> None:
        engine = FlowEngine(executor=_make_recording_executor([]))
        result = await engine.run({"start": "ghost", "steps": {}})
        assert result.status == "failed"
        assert result.error == "Flow definition references unknown step 'ghost'."
        assert result.steps_executed == []

    async def test_an_unknown_next_step_reference_fails_cleanly_mid_run(self) -> None:
        log: ActionLog = []
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "a", "next": "ghost"}},
        }
        engine = FlowEngine(executor=_make_recording_executor(log))
        result = await engine.run(definition)
        assert result.status == "failed"
        assert result.error == "Flow definition references unknown step 'ghost'."
        assert log == ["a"]


class TestMaxStepsGuard:
    async def test_a_real_definition_cycle_is_caught_by_the_hard_step_ceiling(self) -> None:
        # A genuine infinite loop of two unconditional action steps chained back into each
        # other -- no mocking of the ceiling constant. Each step execution here is a
        # negligible in-process async call with no real I/O or sleep, so running the guard
        # out for real (rather than skipping this case) completes in well under a second.
        definition = {
            "start": "s1",
            "steps": {
                "s1": {"kind": "action", "action": "a", "next": "s2"},
                "s2": {"kind": "action", "action": "b", "next": "s1"},
            },
        }
        engine = FlowEngine(executor=_make_recording_executor([]))
        started = time.perf_counter()
        result = await engine.run(definition)
        elapsed = time.perf_counter() - started
        assert result.status == "failed"
        assert result.error == "Exceeded 10000 step executions -- likely a definition cycle."
        assert len(result.steps_executed) == 10_000
        assert elapsed < 10.0
