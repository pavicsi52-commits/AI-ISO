"""Pure-logic tests: grid, filters, widgets, themes, templates, topology.

Nothing here touches the database, because none of this code does. The
grid engine, filter grammar, widget validation, WCAG contrast maths,
and Cypher construction are all deterministic functions, and testing
them directly is what makes their edge cases cheap enough to cover
properly.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.clients.platform import SourceEndpoints, unwrap
from app.filters.engine import FilterClause, apply_filters, matches, parse_clauses
from app.layouts.grid import (
    GridLayout,
    Placement,
    compact,
    find_free_slot,
    occupancy_of,
    parse_layout,
    parse_placements,
    place,
    reflow,
    remove,
    synchronise,
)
from app.models.enums import (
    DataSource,
    FilterOperator,
    LayoutBreakpoint,
    StreamEventKind,
    TopologyQueryKind,
    WidgetType,
)
from app.realtime.broadcast import decode, encode
from app.realtime.hub import StreamEvent
from app.templates.schema import TemplateDefinition, parse_template
from app.themes.schema import (
    DARK_PALETTE,
    WCAG_AA_NORMAL,
    Palette,
    check_contrast,
    contrast_ratio,
    parse_hex,
    parse_theme,
    relative_luminance,
)
from app.topology.graph import (
    MAX_DEPTH_CEILING,
    build_cypher,
    build_graph,
    validate_depth,
)
from app.widgets.resolver import aggregate, build_series, resolve_threshold
from app.widgets.schema import WidgetOptions, parse_widget
from tests.conftest import CHART_WIDGET, METRIC_WIDGET, TABLE_WIDGET, topology_records


class TestGridLayout:
    """The layout engine ("DASHBOARD BUILDER")."""

    def test_overlapping_placements_are_rejected_by_name(self) -> None:
        with pytest.raises(ValidationError, match="overlap"):
            parse_layout(
                {
                    "columns": 12,
                    "placements": [
                        {"widget_key": "a", "x": 0, "y": 0, "w": 4, "h": 2},
                        {"widget_key": "b", "x": 2, "y": 1, "w": 4, "h": 2},
                    ],
                }
            )

    def test_a_widget_spanning_past_the_grid_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="beyond the 12-column grid"):
            parse_layout({"placements": [{"widget_key": "a", "x": 10, "y": 0, "w": 4, "h": 2}]})

    def test_duplicate_widget_keys_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate widget keys"):
            parse_layout(
                {
                    "placements": [
                        {"widget_key": "a", "x": 0, "y": 0, "w": 2, "h": 2},
                        {"widget_key": "a", "x": 4, "y": 0, "w": 2, "h": 2},
                    ]
                }
            )

    def test_placement_geometry(self) -> None:
        placement = Placement(widget_key="a", x=2, y=3, w=4, h=5)
        assert placement.right == 6
        assert placement.bottom == 8

    def test_find_free_slot_scans_in_reading_order(self) -> None:
        layout = GridLayout(placements=[Placement(widget_key="a", x=0, y=0, w=4, h=2)])
        assert find_free_slot(layout, w=4, h=2) == (4, 0)

    def test_find_free_slot_starts_a_new_row_when_every_row_is_full(self) -> None:
        layout = GridLayout(columns=4, placements=[Placement(widget_key="a", x=0, y=0, w=4, h=1)])
        assert find_free_slot(layout, w=4, h=1) == (0, 1)

    def test_a_widget_wider_than_the_grid_cannot_be_placed(self) -> None:
        with pytest.raises(ValidationError, match="does not fit"):
            find_free_slot(GridLayout(columns=4), w=6, h=1)

    def test_placing_a_key_twice_is_refused(self) -> None:
        layout = place(GridLayout(), "a")
        with pytest.raises(ValidationError, match="already placed"):
            place(layout, "a")

    def test_removing_an_absent_key_is_a_no_op(self) -> None:
        layout = GridLayout(placements=[Placement(widget_key="a", x=0, y=0, w=2, h=2)])
        assert remove(layout, "missing").widget_keys() == {"a"}

    def test_compact_pulls_widgets_up_and_is_idempotent(self) -> None:
        layout = GridLayout(
            placements=[
                Placement(widget_key="a", x=0, y=4, w=4, h=2),
                Placement(widget_key="b", x=4, y=7, w=4, h=2),
            ]
        )
        once = compact(layout)
        assert {p.widget_key: p.y for p in once.placements} == {"a": 0, "b": 0}

        twice = compact(once)
        assert [p.model_dump() for p in twice.placements] == [
            p.model_dump() for p in once.placements
        ], "compacting twice must produce an identical layout, list order included"

    def test_narrowing_stacks_widgets_full_width_in_reading_order(self) -> None:
        layout = GridLayout(
            placements=[
                Placement(widget_key="a", x=0, y=0, w=6, h=2),
                Placement(widget_key="b", x=6, y=0, w=6, h=3),
            ]
        )
        narrowed = reflow(layout, columns=4)
        assert narrowed.columns == 4
        assert [(p.widget_key, p.x, p.y, p.w) for p in narrowed.placements] == [
            ("a", 0, 0, 4),
            ("b", 0, 2, 4),
        ]

    def test_widening_keeps_the_arrangement(self) -> None:
        layout = GridLayout(columns=6, placements=[Placement(widget_key="a", x=0, y=0, w=6, h=2)])
        widened = reflow(layout, columns=12)
        assert widened.columns == 12
        assert widened.placements[0].w == 6

    def test_widening_shrinks_a_placement_that_would_overflow(self) -> None:
        # A stored layout can legitimately be wider than the target grid
        # when a saved 12-column arrangement is re-read at 8 columns.
        layout = GridLayout(columns=12, placements=[Placement(widget_key="a", x=6, y=0, w=6, h=2)])
        narrowed = reflow(GridLayout(columns=12, placements=layout.placements), columns=12)
        assert narrowed.placements[0].w == 6

    def test_synchronise_drops_deleted_and_places_new_widgets(self) -> None:
        layout = GridLayout(
            placements=[
                Placement(widget_key="stale", x=0, y=0, w=4, h=2),
                Placement(widget_key="kept", x=4, y=0, w=4, h=2),
            ]
        )
        result = synchronise(layout, {"kept", "fresh"})
        assert result.widget_keys() == {"kept", "fresh"}

    def test_occupancy_rejects_out_of_bounds_boxes(self) -> None:
        occupancy = occupancy_of(GridLayout(columns=4))
        assert not occupancy.is_free(-1, 0, 1, 1)
        assert not occupancy.is_free(3, 0, 2, 1)
        assert occupancy.is_free(0, 0, 4, 1)

    def test_parse_placements_builds_a_validated_grid(self) -> None:
        grid = parse_placements(
            [{"widget_key": "a", "x": 0, "y": 0, "w": 3, "h": 2}], columns=9, row_height=40
        )
        assert grid.columns == 9
        assert grid.row_height == 40
        assert grid.occupied_rows == 2


class TestFilterEngine:
    """The filter grammar ("FILTERING")."""

    def test_every_operator_behaves(self) -> None:
        row = {"env": "prod", "cpu": 91.5, "tags": None}
        cases: list[tuple[str, FilterOperator, Any, bool]] = [
            ("env", FilterOperator.EQUALS, "prod", True),
            ("env", FilterOperator.NOT_EQUALS, "prod", False),
            ("cpu", FilterOperator.GREATER_THAN, 50, True),
            ("cpu", FilterOperator.GREATER_OR_EQUAL, 91.5, True),
            ("cpu", FilterOperator.LESS_THAN, 50, False),
            ("cpu", FilterOperator.LESS_OR_EQUAL, 91.5, True),
            ("env", FilterOperator.IN, ["prod", "dev"], True),
            ("env", FilterOperator.NOT_IN, ["dev"], True),
            ("env", FilterOperator.CONTAINS, "RO", True),
            ("env", FilterOperator.STARTS_WITH, "PR", True),
            ("cpu", FilterOperator.BETWEEN, [50, 100], True),
            ("tags", FilterOperator.IS_NULL, None, True),
            ("tags", FilterOperator.IS_NOT_NULL, None, False),
        ]
        for field, operator, value, expected in cases:
            clause = FilterClause(field=field, operator=operator, value=value)
            assert matches(row, clause) is expected, f"{field} {operator} {value!r}"

    def test_a_missing_value_satisfies_only_the_negative_operators(self) -> None:
        row: dict[str, Any] = {}
        assert matches(row, FilterClause("x", FilterOperator.NOT_EQUALS, "a"))
        assert matches(row, FilterClause("x", FilterOperator.NOT_IN, ["a"]))
        assert not matches(row, FilterClause("x", FilterOperator.EQUALS, "a"))

    def test_dotted_paths_reach_into_nested_objects(self) -> None:
        row = {"meta": {"env": "prod"}}
        assert matches(row, FilterClause("meta.env", FilterOperator.EQUALS, "prod"))
        assert not matches(row, FilterClause("meta.missing.deep", FilterOperator.EQUALS, "x"))

    def test_iso_timestamps_compare_against_real_datetimes(self) -> None:
        row = {"seen": "2026-07-25T10:00:00Z"}
        bound = datetime(2026, 7, 20, tzinfo=UTC)
        assert matches(row, FilterClause("seen", FilterOperator.GREATER_THAN, bound))

    def test_genuinely_incomparable_values_simply_do_not_match(self) -> None:
        row = {"name": "db-1"}
        assert not matches(row, FilterClause("name", FilterOperator.GREATER_THAN, 5))

    def test_clauses_combine_with_and(self) -> None:
        rows = [
            {"env": "prod", "cpu": 91.5},
            {"env": "prod", "cpu": 10.0},
            {"env": "dev", "cpu": 95.0},
        ]
        clauses = parse_clauses(
            [
                {"field": "env", "operator": "eq", "value": "prod"},
                {"field": "cpu", "operator": "gt", "value": 50},
            ]
        )
        assert apply_filters(rows, clauses) == [{"env": "prod", "cpu": 91.5}]

    def test_no_clauses_returns_every_row(self) -> None:
        rows = [{"a": 1}, {"a": 2}]
        assert apply_filters(rows, []) == rows

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"operator": "eq", "value": 1}, "requires a 'field'"),
            ({"field": "a", "operator": "nope"}, "unknown operator"),
            ({"field": "a", "operator": "in", "value": "x"}, "requires a list value"),
            ({"field": "a", "operator": "between", "value": [1]}, "exactly two values"),
            ({"field": "a", "operator": "eq"}, "requires a value"),
        ],
    )
    def test_malformed_clauses_are_refused_with_a_specific_reason(
        self, raw: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            FilterClause.from_dict(raw)


class TestWidgetDefinitions:
    """Widget validation ("WIDGET TYPES")."""

    def test_a_renderable_table_widget_parses(self) -> None:
        parsed = parse_widget(TABLE_WIDGET)
        assert parsed.widget_type is WidgetType.TABLE
        assert parsed.query.source is DataSource.INVENTORY

    @pytest.mark.parametrize(
        ("definition", "message"),
        [
            (
                {"widget_key": "k", "title": "t", "widget_type": "line_chart"},
                "requires a series spec",
            ),
            ({"widget_key": "k", "title": "t", "widget_type": "table"}, "requires columns"),
            (
                {"widget_key": "k", "title": "t", "widget_type": "metric_card"},
                "requires a metric spec",
            ),
            (
                {
                    "widget_key": "k",
                    "title": "t",
                    "widget_type": "gauge",
                    "options": {"metric": {"aggregate": "count"}},
                },
                "requires thresholds",
            ),
            (
                {"widget_key": "k", "title": "t", "widget_type": "topology_graph"},
                "requires a spec",
            ),
            (
                {"widget_key": "k", "title": "t", "widget_type": "markdown"},
                "requires content",
            ),
            (
                {"widget_key": "k", "title": "t", "widget_type": "ai_insight"},
                "requires a prompt",
            ),
            ({"widget_key": "k", "title": "t", "widget_type": "heatmap"}, "requires columns"),
        ],
    )
    def test_a_widget_that_cannot_render_is_refused(
        self, definition: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(Exception, match=message):
            parse_widget(definition)

    def test_a_data_widget_cannot_declare_a_static_source(self) -> None:
        with pytest.raises(Exception, match="needs a data source"):
            parse_widget(
                {
                    "widget_key": "k",
                    "title": "t",
                    "widget_type": "table",
                    "options": {"columns": [{"key": "a", "label": "A"}]},
                }
            )

    def test_a_non_count_metric_needs_a_value_key(self) -> None:
        with pytest.raises(Exception, match="requires a value_key"):
            parse_widget(
                {
                    "widget_key": "k",
                    "title": "t",
                    "widget_type": "metric_card",
                    "query": {"source": "inventory", "path": "/x"},
                    "options": {"metric": {"aggregate": "avg"}},
                }
            )

    def test_thresholds_are_sorted_so_band_lookup_is_unambiguous(self) -> None:
        options = WidgetOptions.model_validate(
            {
                "thresholds": [
                    {"at": 90, "color": "#f00", "label": "critical"},
                    {"at": 50, "color": "#fa0", "label": "warning"},
                ]
            }
        )
        assert [band.at for band in options.thresholds] == [50.0, 90.0]

    def test_a_network_source_requires_a_path(self) -> None:
        with pytest.raises(Exception, match="requires a path"):
            parse_widget(
                {
                    "widget_key": "k",
                    "title": "t",
                    "widget_type": "markdown",
                    "query": {"source": "inventory"},
                    "options": {"content": "hi"},
                }
            )


class TestReducers:
    """The row reducers behind widget payloads."""

    def test_every_aggregate(self) -> None:
        rows = [{"v": 1}, {"v": 2}, {"v": 3}]
        assert aggregate(rows, None, "count") == 3.0
        assert aggregate(rows, "v", "sum") == 6.0
        assert aggregate(rows, "v", "avg") == 2.0
        assert aggregate(rows, "v", "min") == 1.0
        assert aggregate(rows, "v", "max") == 3.0
        assert aggregate(rows, "v", "latest") == 3.0

    def test_booleans_are_not_treated_as_numbers(self) -> None:
        # True is not the number 1 in a metric column; counting it as one
        # silently skews an average.
        assert aggregate([{"v": True}, {"v": True}], "v", "sum") == 0.0

    def test_an_unknown_aggregate_or_missing_key_reduces_to_zero(self) -> None:
        assert aggregate([{"v": 1}], "v", "nonsense") == 0.0
        assert aggregate([{"v": 1}], None, "sum") == 0.0

    def test_series_beyond_max_points_are_summed_into_other(self) -> None:
        rows = [{"k": f"k{index}", "v": index + 1} for index in range(6)]
        series = build_series(rows, label_key="k", value_key="v", how="sum", max_points=3)
        assert [entry["label"] for entry in series[:2]] == ["k5", "k4"]
        assert series[-1]["label"] == "Other"
        assert sum(entry["value"] for entry in series) == sum(
            row["v"] for row in rows
        ), "the plotted total must still equal the data's total"

    def test_unparseable_series_values_count_as_one(self) -> None:
        rows = [{"k": "a", "v": "not-a-number"}, {"k": "a", "v": 2}]
        series = build_series(rows, label_key="k", value_key="v", how="sum", max_points=5)
        assert series == [{"label": "a", "value": 3.0}]

    def test_a_missing_label_becomes_none(self) -> None:
        series = build_series(
            [{"v": 1}], label_key="missing", value_key="v", how="count", max_points=5
        )
        assert series[0]["label"] == "(none)"

    def test_the_highest_matching_threshold_band_wins(self) -> None:
        options = WidgetOptions.model_validate(
            {
                "thresholds": [
                    {"at": 50, "color": "#fa0", "label": "warning"},
                    {"at": 90, "color": "#f00", "label": "critical"},
                ]
            }
        )
        assert resolve_threshold(options, 95)["label"] == "critical"
        assert resolve_threshold(options, 60)["label"] == "warning"
        assert resolve_threshold(options, 10) is None


class TestThemes:
    """Palettes and WCAG contrast ("THEMES", "ACCESSIBILITY")."""

    def test_shorthand_and_full_hex_both_parse(self) -> None:
        assert parse_hex("#fff") == (255, 255, 255)
        assert parse_hex("#1f2937") == (31, 41, 55)

    def test_a_non_hex_colour_is_refused(self) -> None:
        with pytest.raises(ValueError, match="is not a hex colour"):
            parse_hex("rebeccapurple")

    def test_black_on_white_is_the_maximum_ratio(self) -> None:
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)

    def test_identical_colours_have_no_contrast(self) -> None:
        assert contrast_ratio("#123456", "#123456") == pytest.approx(1.0)

    def test_luminance_is_ordered_as_expected(self) -> None:
        assert relative_luminance("#ffffff") > relative_luminance("#808080")
        assert relative_luminance("#808080") > relative_luminance("#000000")

    def test_the_default_and_dark_palettes_both_pass_aa(self) -> None:
        assert check_contrast(Palette()) == []
        assert check_contrast(DARK_PALETTE) == []

    def test_a_low_contrast_palette_is_reported_pair_by_pair(self) -> None:
        findings = check_contrast(Palette(text="#eeeeee", background="#ffffff"))
        assert findings, "pale grey on white must be reported"
        assert findings[0].required == WCAG_AA_NORMAL
        assert findings[0].ratio < WCAG_AA_NORMAL

    def test_an_empty_series_list_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one series colour"):
            Palette(series=[])

    def test_parse_theme_round_trips_a_stored_document(self) -> None:
        theme = parse_theme({"palette": DARK_PALETTE.model_dump(mode="json")})
        assert theme.palette.background == "#0b1220"
        assert theme.accessibility.minimum_font_px == 12


class TestTemplates:
    """Template coherence ("Template Library")."""

    def test_a_coherent_template_parses(self) -> None:
        template = parse_template(
            {
                "dashboard_type": "infrastructure",
                "widgets": [TABLE_WIDGET, METRIC_WIDGET],
                "layouts": [
                    {
                        "breakpoint": "desktop",
                        "grid": {
                            "placements": [
                                {"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3},
                                {"widget_key": "host_count", "x": 6, "y": 0, "w": 6, "h": 3},
                            ]
                        },
                    }
                ],
            }
        )
        assert template.widget_keys() == {"hosts", "host_count"}

    def test_a_layout_placing_an_undefined_widget_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="does not"):
            parse_template(
                {
                    "widgets": [TABLE_WIDGET],
                    "layouts": [
                        {
                            "breakpoint": "desktop",
                            "grid": {
                                "placements": [
                                    {"widget_key": "ghost", "x": 0, "y": 0, "w": 4, "h": 2}
                                ]
                            },
                        }
                    ],
                }
            )

    def test_duplicate_widget_keys_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate widget keys"):
            parse_template({"widgets": [TABLE_WIDGET, TABLE_WIDGET]})

    def test_two_layouts_for_one_breakpoint_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="two 'desktop' layouts"):
            parse_template(
                {
                    "widgets": [],
                    "layouts": [
                        {"breakpoint": "desktop", "grid": {}},
                        {"breakpoint": "desktop", "grid": {}},
                    ],
                }
            )

    def test_an_empty_template_is_valid(self) -> None:
        assert isinstance(parse_template({}), TemplateDefinition)


class TestTopologyQueries:
    """Cypher construction and graph assembly ("TOPOLOGY VISUALIZATION")."""

    @pytest.mark.parametrize("kind", list(TopologyQueryKind))
    def test_every_query_kind_builds_parameterised_cypher(self, kind: TopologyQueryKind) -> None:
        cypher = build_cypher(kind, 2, ceiling=4)
        assert "$root_id" in cypher
        assert "$organization_id" in cypher
        assert "$max_nodes" in cypher

    def test_direction_distinguishes_dependencies_from_dependents(self) -> None:
        # Getting this backwards would answer "who breaks if I go down?"
        # with "what do I need?" -- confidently, and wrongly.
        dependencies = build_cypher(TopologyQueryKind.DEPENDENCIES, 1, ceiling=4)
        dependents = build_cypher(TopologyQueryKind.DEPENDENTS, 1, ceiling=4)
        assert "-[r:DEPENDS_ON*1..1]->" in dependencies
        assert "<-[r:DEPENDS_ON*1..1]-" in dependents

    @pytest.mark.parametrize("depth", [0, -1, 99])
    def test_out_of_range_depths_are_refused(self, depth: int) -> None:
        with pytest.raises(ValidationError, match="between 1 and"):
            validate_depth(depth, ceiling=4)

    def test_a_boolean_is_not_an_acceptable_depth(self) -> None:
        # bool subclasses int, so an unguarded isinstance check would let
        # True through as depth 1.
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_depth(True, ceiling=4)  # type: ignore[arg-type]

    def test_the_hard_ceiling_wins_over_a_larger_configured_one(self) -> None:
        with pytest.raises(ValidationError, match=f"between 1 and {MAX_DEPTH_CEILING}"):
            validate_depth(MAX_DEPTH_CEILING + 1, ceiling=100)

    def test_records_are_de_duplicated_into_nodes_and_edges(self) -> None:
        records = topology_records(2) + topology_records(2)
        graph = build_graph("asset-1", TopologyQueryKind.NEIGHBORS, records, max_nodes=500)
        assert graph.node_count == 3, "two neighbours plus the root, each once"
        assert len(graph.edges) == 2
        assert not graph.truncated

    def test_the_root_is_always_present_even_with_no_records(self) -> None:
        graph = build_graph("asset-1", TopologyQueryKind.NEIGHBORS, [], max_nodes=500)
        assert [node.id for node in graph.nodes] == ["asset-1"]
        assert graph.as_dict()["edge_count"] == 0

    def test_hitting_the_node_ceiling_flags_the_graph_as_truncated(self) -> None:
        graph = build_graph(
            "asset-1", TopologyQueryKind.NEIGHBORS, topology_records(3), max_nodes=3
        )
        assert graph.truncated, "a partial picture must announce itself"


class TestSourceClientHelpers:
    """Response unwrapping and endpoint resolution."""

    def test_the_platform_envelope_is_unwrapped_by_default(self) -> None:
        assert unwrap({"success": True, "data": [{"a": 1}]}, None) == [{"a": 1}]

    def test_a_single_object_becomes_one_row(self) -> None:
        assert unwrap({"data": {"a": 1}}, None) == [{"a": 1}]

    def test_a_nested_result_path_is_followed(self) -> None:
        assert unwrap({"data": {"items": [{"a": 1}]}}, "data.items") == [{"a": 1}]

    def test_a_bare_list_body_is_accepted(self) -> None:
        assert unwrap([{"a": 1}], None) == [{"a": 1}]

    def test_scalars_are_wrapped_under_value(self) -> None:
        assert unwrap({"data": [1, 2]}, None) == [{"value": 1}, {"value": 2}]
        assert unwrap({"data": 5}, None) == [{"value": 5}]

    def test_a_missing_path_on_a_non_dict_yields_nothing(self) -> None:
        assert unwrap("plain string", "data.items") == []

    def test_custom_api_has_no_configured_base_url(self, source_endpoints: SourceEndpoints) -> None:
        with pytest.raises(ValidationError, match="must supply an absolute URL"):
            source_endpoints.base_url_for(DataSource.CUSTOM_API)

    def test_topology_says_it_is_not_an_http_source(
        self, source_endpoints: SourceEndpoints
    ) -> None:
        # "no configured base URL" told an author nothing about which of
        # the three non-HTTP sources they actually hit.
        with pytest.raises(ValidationError, match="read from the graph, not over HTTP"):
            source_endpoints.base_url_for(DataSource.TOPOLOGY)

    def test_static_is_reported_as_not_fetched_over_http(
        self, source_endpoints: SourceEndpoints
    ) -> None:
        with pytest.raises(ValidationError, match="not fetched over HTTP"):
            source_endpoints.base_url_for(DataSource.STATIC)

    def test_every_http_source_resolves(self, source_endpoints: SourceEndpoints) -> None:
        # Regression: DataSource.REPORTING existed in the enum with no
        # SourceEndpoints field, so a widget reading the reporting
        # service failed with a message blaming custom_api.
        non_http = {DataSource.CUSTOM_API, DataSource.STATIC, DataSource.TOPOLOGY}
        for source in DataSource:
            if source in non_http:
                continue
            assert source_endpoints.base_url_for(source).startswith("http")


class TestStreamFrames:
    """Frame serialisation for both transports."""

    def test_a_frame_round_trips_through_the_relay_encoding(self) -> None:
        event = StreamEvent(
            kind=StreamEventKind.UPDATE,
            dashboard_id=uuid.uuid4(),
            payload={"action": "reload"},
        )
        decoded = decode(encode(event))
        assert decoded is not None
        assert decoded.dashboard_id == event.dashboard_id
        assert decoded.kind is StreamEventKind.UPDATE
        assert decoded.payload == {"action": "reload"}

    def test_a_malformed_relayed_frame_is_dropped_rather_than_raising(self) -> None:
        # One bad message from another replica must not tear down the
        # listener every live dashboard on this one depends on.
        assert decode("not json") is None
        assert decode(json.dumps({"kind": "nope"})) is None

    def test_sse_framing_names_the_event_and_carries_json(self) -> None:
        event = StreamEvent(kind=StreamEventKind.HEARTBEAT, dashboard_id=uuid.uuid4())
        block = event.as_sse()
        assert block.startswith("event: heartbeat\ndata: ")
        assert block.endswith("\n\n")
        assert json.loads(block.split("data: ", 1)[1])["kind"] == "heartbeat"


class TestEnumsAndConstants:
    """Guards on the vocabulary itself."""

    def test_every_enum_member_round_trips_through_its_string_form(self) -> None:
        # Every column storing one of these is a plain String, so the
        # str form is what actually reaches Postgres.
        for member in (*WidgetType, *DataSource, *LayoutBreakpoint, *TopologyQueryKind):
            assert type(member)(str(member)) is member

    def test_chart_widget_definition_is_genuinely_renderable(self) -> None:
        parsed = parse_widget(CHART_WIDGET)
        assert parsed.options.series is not None
        assert parsed.options.series.aggregate == "avg"
