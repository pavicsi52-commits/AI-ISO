"""Telemetry spans -- a real OTel tracer wired to an in-memory exporter.

Not a mock: a genuine ``TracerProvider`` from the OpenTelemetry SDK, with
a ``SimpleSpanProcessor`` feeding an ``InMemorySpanExporter`` -- so each
finished span's actual name and attributes can be read back and asserted
on, rather than only proving the context manager does not raise. This is
exactly the check that would have caught the ``attributes={...}`` defect
this service's own ``app/telemetry/tracing.py`` docstring describes:
``start_span``'s own signature is ``start_span(tracer, name, *,
span_type=None, **attributes)`` -- there is no parameter actually named
``attributes``, only that catch-all, and a call site that passed one
anyway would silently drop every attribute onto the floor instead of
raising. Every attribute asserted below is read directly out of the
exported span, never inferred from "the context manager did not raise."
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer
from shared_core.telemetry.constants import MASKED_ATTRIBUTE_VALUE

from app.telemetry.tracing import (
    trace_activation,
    trace_execution,
    trace_health_check,
    trace_installation,
    trace_marketplace_search,
    trace_package_verification,
    trace_publish,
    trace_rollback,
    trace_upgrade,
    trace_worker_tick,
)


def _tracer() -> tuple[Tracer, InMemorySpanExporter]:
    """A real tracer whose finished spans land in an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class TestSpans:
    def test_installation_carries_plugin_id_and_organization_id(self) -> None:
        tracer, exporter = _tracer()
        with trace_installation(tracer, plugin_id="plugin-1", organization_id="org-1") as span:
            assert span is not None
        finished = exporter.get_finished_spans()
        assert len(finished) == 1
        assert finished[0].name == "marketplace.plugin.install"
        attributes = dict(finished[0].attributes or {})
        assert attributes["marketplace.plugin_id"] == "plugin-1"
        assert attributes["marketplace.organization_id"] == "org-1"
        assert attributes["span.type"] == "rest_api"

    def test_activation_carries_installation_id(self) -> None:
        tracer, exporter = _tracer()
        with trace_activation(tracer, installation_id="install-1"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.plugin.activate"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.installation_id"] == "install-1"
        assert attributes["span.type"] == "rest_api"

    def test_execution_carries_installation_id_and_timed_out(self) -> None:
        tracer, exporter = _tracer()
        with trace_execution(tracer, installation_id="install-1", timed_out=False):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.plugin.execute"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.installation_id"] == "install-1"
        assert attributes["marketplace.timed_out"] is False
        assert attributes["span.type"] == "background_job"

    def test_execution_carries_timed_out_true(self) -> None:
        # `False` is falsy but must still be present, distinguishing "did
        # not time out" from "field never set."
        tracer, exporter = _tracer()
        with trace_execution(tracer, installation_id="install-2", timed_out=True):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["marketplace.timed_out"] is True

    def test_upgrade_carries_installation_and_both_version_numbers(self) -> None:
        tracer, exporter = _tracer()
        with trace_upgrade(
            tracer,
            installation_id="install-1",
            from_version_number="1.0.0",
            to_version_number="1.1.0",
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.plugin.upgrade"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.installation_id"] == "install-1"
        assert attributes["marketplace.from_version_number"] == "1.0.0"
        assert attributes["marketplace.to_version_number"] == "1.1.0"
        assert attributes["span.type"] == "rest_api"

    def test_rollback_carries_installation_and_both_version_numbers(self) -> None:
        tracer, exporter = _tracer()
        with trace_rollback(
            tracer,
            installation_id="install-1",
            from_version_number="1.1.0",
            to_version_number="1.0.0",
        ):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.plugin.rollback"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.installation_id"] == "install-1"
        assert attributes["marketplace.from_version_number"] == "1.1.0"
        assert attributes["marketplace.to_version_number"] == "1.0.0"
        assert attributes["span.type"] == "rest_api"

    def test_marketplace_search_carries_query_and_results_returned(self) -> None:
        tracer, exporter = _tracer()
        with trace_marketplace_search(tracer, query="aws", results_returned=3):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.search"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.query"] == "aws"
        assert attributes["marketplace.results_returned"] == 3
        assert attributes["span.type"] == "rest_api"

    def test_marketplace_search_with_no_query_carries_empty_string(self) -> None:
        tracer, exporter = _tracer()
        with trace_marketplace_search(tracer, query=None, results_returned=0):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["marketplace.query"] == ""
        assert attributes["marketplace.results_returned"] == 0

    def test_package_verification_carries_package_id_and_verified(self) -> None:
        tracer, exporter = _tracer()
        with trace_package_verification(tracer, package_id="package-1", verified=True):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.package.verify"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.package_id"] == "package-1"
        assert attributes["marketplace.verified"] is True
        assert attributes["span.type"] == "rest_api"

    def test_package_verification_carries_verified_false(self) -> None:
        tracer, exporter = _tracer()
        with trace_package_verification(tracer, package_id="package-2", verified=False):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["marketplace.verified"] is False

    def test_health_check_carries_installation_id_and_status(self) -> None:
        tracer, exporter = _tracer()
        with trace_health_check(tracer, installation_id="install-1", status="healthy"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.health.check"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.installation_id"] == "install-1"
        assert attributes["marketplace.status"] == "healthy"
        assert attributes["span.type"] == "background_job"

    def test_worker_tick_carries_worker_name_and_processed_count(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="health_probe_sweep", processed=5):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.worker.tick"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.worker"] == "health_probe_sweep"
        assert attributes["marketplace.processed"] == 5
        assert attributes["span.type"] == "background_job"

    def test_worker_tick_carries_zero_processed(self) -> None:
        tracer, exporter = _tracer()
        with trace_worker_tick(tracer, worker="statistics_rollup", processed=0):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["marketplace.processed"] == 0

    def test_publish_carries_the_event_name(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="PluginInstalled"):
            pass
        finished = exporter.get_finished_spans()[0]
        assert finished.name == "marketplace.event.publish"
        attributes = dict(finished.attributes or {})
        assert attributes["marketplace.event"] == "PluginInstalled"
        assert attributes["span.type"] == "background_job"

    def test_extra_attributes_pass_through_alongside_the_named_ones(self) -> None:
        tracer, exporter = _tracer()
        with trace_publish(tracer, event_name="PluginRemoved", correlation_id="corr-123"):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["marketplace.event"] == "PluginRemoved"
        assert attributes["correlation_id"] == "corr-123"

    def test_extra_attribute_with_a_sensitive_looking_key_is_masked(self) -> None:
        # `start_span` runs every attribute through
        # `shared_core.telemetry.span.sanitize_attributes` before it ever
        # reaches the span -- proof this module's own extra ``**attributes``
        # pass-through actually flows through that masking, not just that
        # the named `marketplace.*` attributes happen to look safe.
        tracer, exporter = _tracer()
        with trace_installation(
            tracer, plugin_id="plugin-1", organization_id="org-1", api_key="super-secret-value"
        ):
            pass
        attributes = dict(exporter.get_finished_spans()[0].attributes or {})
        assert attributes["api_key"] == MASKED_ATTRIBUTE_VALUE
        assert "super-secret-value" not in attributes.values()

    def test_an_exception_inside_a_span_still_propagates(self) -> None:
        tracer, _exporter = _tracer()
        with (
            pytest.raises(RuntimeError, match="boom"),
            trace_installation(tracer, plugin_id="plugin-1", organization_id="org-1"),
        ):
            raise RuntimeError("boom")

    def test_the_span_that_raised_is_still_exported(self) -> None:
        # `start_span` uses a plain `with`, not a try/except that
        # swallows -- the span should still end (and export) even though
        # the exception propagates past this helper.
        tracer, exporter = _tracer()
        with (
            pytest.raises(RuntimeError),
            trace_worker_tick(tracer, worker="review_moderation_sweep", processed=0),
        ):
            raise RuntimeError("boom")
        assert len(exporter.get_finished_spans()) == 1
