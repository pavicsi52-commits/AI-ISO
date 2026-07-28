"""The grid layout engine ("DASHBOARD BUILDER").

Drag-and-drop, resizing, and responsive reflow all reduce to one
question: *is this arrangement valid, and if not, what is the nearest
valid one?* This module answers it.

**Overlap is rejected, not silently resolved.** A layout where two
widgets claim the same cell renders differently in every grid
implementation, so it is refused at save time with the specific pair
named. Callers that want automatic placement ask for it explicitly via
:func:`compact` or :func:`find_free_slot`.

**Reflow is deterministic.** Narrowing to a phone breakpoint reorders
widgets by reading order (top-to-bottom, then left-to-right) and
stacks them full width. That is boring on purpose: a user who saves a
mobile layout should get the same result every time, and can then
adjust it deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator
from shared_core.exceptions.validation import ValidationError

MIN_SPAN = 1
"""A widget must occupy at least one cell in each dimension."""


class Placement(BaseModel):
    """One widget's position and size on the grid."""

    widget_key: str = Field(min_length=1, max_length=64)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=MIN_SPAN)
    h: int = Field(ge=MIN_SPAN)

    @property
    def right(self) -> int:
        """One past the last column this placement occupies."""
        return self.x + self.w

    @property
    def bottom(self) -> int:
        """One past the last row this placement occupies."""
        return self.y + self.h

    def overlaps(self, other: Placement) -> bool:
        """Whether two placements share any cell."""
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )


class GridLayout(BaseModel):
    """A complete arrangement for one breakpoint."""

    columns: int = Field(default=12, ge=1, le=48)
    row_height: int = Field(default=60, ge=10, le=500)
    placements: list[Placement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_grid(self) -> GridLayout:
        """Reject duplicate keys, out-of-bounds spans, and overlaps."""
        keys = [placement.widget_key for placement in self.placements]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"Duplicate widget keys in layout: {', '.join(duplicates)}.")

        for placement in self.placements:
            if placement.right > self.columns:
                raise ValueError(
                    f"Widget {placement.widget_key!r} spans to column {placement.right}, "
                    f"beyond the {self.columns}-column grid."
                )

        for index, first in enumerate(self.placements):
            for second in self.placements[index + 1 :]:
                if first.overlaps(second):
                    raise ValueError(
                        f"Widgets {first.widget_key!r} and {second.widget_key!r} overlap."
                    )
        return self

    @property
    def occupied_rows(self) -> int:
        """How many rows the arrangement actually uses."""
        return max((placement.bottom for placement in self.placements), default=0)

    def widget_keys(self) -> set[str]:
        """Every widget key placed on this grid."""
        return {placement.widget_key for placement in self.placements}


@dataclass(frozen=True, slots=True)
class Occupancy:
    """A read-only view of which cells are taken."""

    columns: int
    cells: frozenset[tuple[int, int]]

    def is_free(self, x: int, y: int, w: int, h: int) -> bool:
        """Whether a ``w * h`` box at ``(x, y)`` fits without collision."""
        if x < 0 or y < 0 or x + w > self.columns:
            return False
        return all(
            (column, row) not in self.cells for column in range(x, x + w) for row in range(y, y + h)
        )


def occupancy_of(layout: GridLayout) -> Occupancy:
    """Build the occupancy map for *layout*."""
    cells = {
        (column, row)
        for placement in layout.placements
        for column in range(placement.x, placement.right)
        for row in range(placement.y, placement.bottom)
    }
    return Occupancy(columns=layout.columns, cells=frozenset(cells))


def find_free_slot(layout: GridLayout, *, w: int, h: int) -> tuple[int, int]:
    """The first free ``w * h`` slot, scanning in reading order.

    Scans row by row so a newly added widget lands where a person would
    naturally expect -- the first gap, top-left first -- rather than at
    an arbitrary coordinate or always at the bottom.

    Raises:
        ValidationError: If the widget is wider than the grid.
    """
    if w > layout.columns:
        raise ValidationError(
            f"A widget {w} columns wide does not fit a {layout.columns}-column grid."
        )
    occupancy = occupancy_of(layout)
    for row in range(layout.occupied_rows + 1):
        for column in range(layout.columns - w + 1):
            if occupancy.is_free(column, row, w, h):
                return column, row
    # Every existing row is full; start a fresh one below.
    return 0, layout.occupied_rows


def place(layout: GridLayout, widget_key: str, *, w: int = 4, h: int = 3) -> GridLayout:
    """Return a copy of *layout* with *widget_key* added at the first gap.

    Raises:
        ValidationError: If the key is already placed, or it cannot fit.
    """
    if widget_key in layout.widget_keys():
        raise ValidationError(f"Widget {widget_key!r} is already placed on this layout.")
    x, y = find_free_slot(layout, w=w, h=h)
    return GridLayout(
        columns=layout.columns,
        row_height=layout.row_height,
        placements=[*layout.placements, Placement(widget_key=widget_key, x=x, y=y, w=w, h=h)],
    )


def remove(layout: GridLayout, widget_key: str) -> GridLayout:
    """Return a copy of *layout* without *widget_key*.

    Removing an absent key is a no-op rather than an error: deleting a
    widget should not fail because its placement was already gone.
    """
    return GridLayout(
        columns=layout.columns,
        row_height=layout.row_height,
        placements=[p for p in layout.placements if p.widget_key != widget_key],
    )


def compact(layout: GridLayout) -> GridLayout:
    """Pull every widget upward into the gaps above it.

    Grid UIs do this after a drag so the arrangement has no floating
    holes. Widgets are processed in reading order, which is what makes
    the result stable: compacting twice yields the same layout.
    """
    ordered = sorted(layout.placements, key=lambda p: (p.y, p.x))
    settled: list[Placement] = []
    for placement in ordered:
        current = GridLayout(
            columns=layout.columns, row_height=layout.row_height, placements=settled
        )
        occupancy = occupancy_of(current)
        row = placement.y
        while row > 0 and occupancy.is_free(placement.x, row - 1, placement.w, placement.h):
            row -= 1
        settled.append(
            Placement(
                widget_key=placement.widget_key,
                x=placement.x,
                y=row,
                w=placement.w,
                h=placement.h,
            )
        )
    # Returned in canonical reading order so compacting twice yields an
    # identical layout, list order included -- otherwise a no-op save
    # would still produce a diff.
    settled.sort(key=lambda p: (p.y, p.x))
    return GridLayout(columns=layout.columns, row_height=layout.row_height, placements=settled)


def reflow(layout: GridLayout, *, columns: int) -> GridLayout:
    """Re-arrange *layout* for a grid of a different width.

    Widening keeps the existing arrangement wherever it still fits.
    Narrowing stacks widgets full width in reading order, because
    proportionally scaling a 12-column layout into 4 columns produces
    unreadable slivers -- a phone wants one widget per row.
    """
    if columns >= layout.columns:
        placements = [
            (
                p
                if p.right <= columns
                else Placement(
                    widget_key=p.widget_key,
                    x=p.x,
                    y=p.y,
                    w=min(p.w, columns - p.x),
                    h=p.h,
                )
            )
            for p in layout.placements
        ]
        return compact(
            GridLayout(columns=columns, row_height=layout.row_height, placements=placements)
        )

    ordered = sorted(layout.placements, key=lambda p: (p.y, p.x))
    stacked: list[Placement] = []
    row = 0
    for placement in ordered:
        stacked.append(
            Placement(widget_key=placement.widget_key, x=0, y=row, w=columns, h=placement.h)
        )
        row += placement.h
    return GridLayout(columns=columns, row_height=layout.row_height, placements=stacked)


def parse_layout(raw: dict[str, Any]) -> GridLayout:
    """Parse a stored layout, raising the platform's own error.

    Raises:
        ValidationError: If the arrangement is malformed, has duplicate
            keys, overflows the grid, or contains overlapping widgets.
    """
    try:
        return GridLayout.model_validate(raw)
    except Exception as exc:
        raise ValidationError(f"Invalid dashboard layout: {exc}") from exc


def parse_placements(
    placements: list[dict[str, Any]], *, columns: int, row_height: int
) -> GridLayout:
    """Build and validate a layout from stored placement rows."""
    return parse_layout({"columns": columns, "row_height": row_height, "placements": placements})


def synchronise(layout: GridLayout, widget_keys: set[str]) -> GridLayout:
    """Reconcile a layout against the widgets that actually exist.

    Placements for deleted widgets are dropped and newly added widgets
    are placed in the first free slot. Without this, deleting a widget
    would leave a hole that renders as a gap forever, and adding one
    would leave it invisible until someone dragged it in.
    """
    result = GridLayout(
        columns=layout.columns,
        row_height=layout.row_height,
        placements=[p for p in layout.placements if p.widget_key in widget_keys],
    )
    for key in sorted(widget_keys - result.widget_keys()):
        result = place(result, key)
    return result


__all__ = [
    "MIN_SPAN",
    "GridLayout",
    "Occupancy",
    "Placement",
    "compact",
    "find_free_slot",
    "occupancy_of",
    "parse_layout",
    "parse_placements",
    "place",
    "reflow",
    "remove",
    "synchronise",
]
