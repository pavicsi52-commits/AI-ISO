"""Enterprise Telemetry Framework.

Complete end-to-end observability for AI-IOS
(docs/024_Enterprise_Telemetry_Framework.md.txt "OBJECTIVE"): Distributed
Tracing, OpenTelemetry Integration, Context Propagation, Span Management,
Correlation IDs, Request IDs, Performance Profiling, Trace Analytics,
Metrics Correlation, Log Correlation, Trace Export, Trace Search,
Performance Baselines.

Naming note: the ``@trace``/``@span`` decorators
(:mod:`shared_core.telemetry.decorators`) share their bare names with
this package's own ``trace``/``span`` *submodules*
(:mod:`shared_core.telemetry.trace`'s ``get_tracer``/``start_root_trace``,
:mod:`shared_core.telemetry.span`'s ``SpanType``/``start_span``) --
re-exporting both under the same top-level name would silently shadow
one or the other. The submodules' own primitives win the bare names
here since they're this framework's foundation; the two decorators
remain available at their literal spec names via
``from shared_core.telemetry.decorators import trace, span``.
"""

from shared_core.telemetry.ai import trace_ai_request, trace_model_inference
from shared_core.telemetry.analytics import (
    AnalyticsSpanProcessor,
    SpanEdge,
    TraceRecorder,
    TraceSummary,
)
from shared_core.telemetry.automation import trace_automation_step
from shared_core.telemetry.cache import trace_cache_access
from shared_core.telemetry.connector import trace_connector_execution
from shared_core.telemetry.context import TraceContext, current_span_ids, current_trace_context
from shared_core.telemetry.database import trace_database_query
from shared_core.telemetry.decorators import (
    measure,
    profile,
    track_ai,
    track_automation,
    track_cache,
    track_connector,
    track_database,
    track_plugin,
    track_queue,
    track_storage,
    track_validation,
    track_workflow,
)
from shared_core.telemetry.exceptions import (
    ExporterConfigurationError,
    PropagationError,
    SamplingConfigurationError,
    SpanContextError,
    SpanExportError,
)
from shared_core.telemetry.exporters import (
    JsonFileSpanExporter,
    console_exporter,
    create_exporter,
    json_file_exporter,
    otlp_exporter,
)
from shared_core.telemetry.factory import create_telemetry_framework
from shared_core.telemetry.health import TelemetryHealthReport, calculate_telemetry_health
from shared_core.telemetry.helpers import (
    format_span_id,
    format_trace_id,
    is_valid_span_id,
    is_valid_trace_id,
)
from shared_core.telemetry.logs import correlate_logs_with_span
from shared_core.telemetry.manager import TelemetryManager
from shared_core.telemetry.metrics import (
    cache_time_seconds,
    database_time_seconds,
    observe_with_trace_exemplar,
    storage_time_seconds,
)
from shared_core.telemetry.middleware import TracingMiddleware
from shared_core.telemetry.plugin import trace_plugin_execution
from shared_core.telemetry.profiling import DeepProfile, ProfileResult, measure_duration_ms
from shared_core.telemetry.propagation import (
    extract_context,
    inject_context,
    restore_context,
    use_context,
)
from shared_core.telemetry.provider import build_resource, configure_tracing, shutdown_tracing
from shared_core.telemetry.queue import trace_queue_consume, trace_queue_publish
from shared_core.telemetry.request import (
    current_correlation_id,
    current_request_id,
    tag_span_with_request_ids,
)
from shared_core.telemetry.sampling import (
    AdaptiveSampler,
    DynamicSampler,
    RuleBasedSampler,
    SamplingRule,
    always_sample,
    environment_based_sampler,
    never_sample,
    probability_sampler,
)
from shared_core.telemetry.scheduler import trace_scheduler_job
from shared_core.telemetry.span import SpanType, sanitize_attributes, start_span
from shared_core.telemetry.storage import trace_file_download, trace_file_upload
from shared_core.telemetry.trace import get_tracer, is_traced, start_root_trace
from shared_core.telemetry.validation import trace_validation_step
from shared_core.telemetry.worker import trace_background_job
from shared_core.telemetry.workflow import trace_workflow_execution, trace_workflow_step

__all__ = [
    "AdaptiveSampler",
    "AnalyticsSpanProcessor",
    "DeepProfile",
    "DynamicSampler",
    "ExporterConfigurationError",
    "JsonFileSpanExporter",
    "ProfileResult",
    "PropagationError",
    "RuleBasedSampler",
    "SamplingConfigurationError",
    "SamplingRule",
    "SpanContextError",
    "SpanEdge",
    "SpanExportError",
    "SpanType",
    "TelemetryHealthReport",
    "TelemetryManager",
    "TraceContext",
    "TraceRecorder",
    "TraceSummary",
    "TracingMiddleware",
    "always_sample",
    "build_resource",
    "cache_time_seconds",
    "calculate_telemetry_health",
    "configure_tracing",
    "console_exporter",
    "correlate_logs_with_span",
    "create_exporter",
    "create_telemetry_framework",
    "current_correlation_id",
    "current_request_id",
    "current_span_ids",
    "current_trace_context",
    "database_time_seconds",
    "environment_based_sampler",
    "extract_context",
    "format_span_id",
    "format_trace_id",
    "get_tracer",
    "inject_context",
    "is_traced",
    "is_valid_span_id",
    "is_valid_trace_id",
    "json_file_exporter",
    "measure",
    "measure_duration_ms",
    "never_sample",
    "observe_with_trace_exemplar",
    "otlp_exporter",
    "probability_sampler",
    "profile",
    "restore_context",
    "sanitize_attributes",
    "shutdown_tracing",
    "start_root_trace",
    "start_span",
    "storage_time_seconds",
    "tag_span_with_request_ids",
    "trace_ai_request",
    "trace_automation_step",
    "trace_background_job",
    "trace_cache_access",
    "trace_connector_execution",
    "trace_database_query",
    "trace_file_download",
    "trace_file_upload",
    "trace_model_inference",
    "trace_plugin_execution",
    "trace_queue_consume",
    "trace_queue_publish",
    "trace_scheduler_job",
    "trace_validation_step",
    "trace_workflow_execution",
    "trace_workflow_step",
    "track_ai",
    "track_automation",
    "track_cache",
    "track_connector",
    "track_database",
    "track_plugin",
    "track_queue",
    "track_storage",
    "track_validation",
    "track_workflow",
    "use_context",
]
