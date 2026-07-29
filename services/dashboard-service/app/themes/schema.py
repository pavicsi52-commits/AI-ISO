"""Theme palettes, branding, and accessibility ("THEMES").

A theme's ``palette`` and ``branding`` are JSON columns, so this module
is what keeps them structured. Validating on write means a theme that
would render unreadable text is refused at authoring time rather than
discovered by whoever opens the dashboard.

**Contrast is checked, not assumed.** A corporate palette with pale
grey text on white is a real accessibility failure that no amount of
"accessibility options" elsewhere fixes. :func:`contrast_ratio`
implements the WCAG 2.1 relative-luminance formula, and
:func:`check_contrast` reports which pairs fall below AA -- reported
rather than rejected, because a brand colour is sometimes non-
negotiable and the honest thing is to make the shortfall visible.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

WCAG_AA_NORMAL = 4.5
"""Minimum contrast ratio for normal text under WCAG 2.1 AA."""

WCAG_AA_LARGE = 3.0
"""Minimum contrast ratio for large text under WCAG 2.1 AA."""

_SRGB_THRESHOLD = 0.03928
_LUMINANCE_OFFSET = 0.055
_SHORTHAND_HEX_LENGTH = 3
"""Digits in the ``#rgb`` shorthand form, which expands to ``#rrggbb``."""


def _channel_luminance(channel: int) -> float:
    """Linearise one 0-255 sRGB channel, per WCAG 2.1."""
    value = channel / 255.0
    if value <= _SRGB_THRESHOLD:
        return value / 12.92
    return float(((value + _LUMINANCE_OFFSET) / (1 + _LUMINANCE_OFFSET)) ** 2.4)


def parse_hex(color: str) -> tuple[int, int, int]:
    """Parse ``#rgb`` or ``#rrggbb`` into channel values.

    Raises:
        ValueError: If the string is not a hex colour.
    """
    if not _HEX.match(color):
        raise ValueError(f"{color!r} is not a hex colour like '#1f2937'.")
    body = color.lstrip("#")
    if len(body) == _SHORTHAND_HEX_LENGTH:
        body = "".join(character * 2 for character in body)
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def relative_luminance(color: str) -> float:
    """The WCAG relative luminance of a hex colour."""
    red, green, blue = parse_hex(color)
    return (
        0.2126 * _channel_luminance(red)
        + 0.7152 * _channel_luminance(green)
        + 0.0722 * _channel_luminance(blue)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    """The WCAG 2.1 contrast ratio between two colours.

    Ranges from 1 (identical) to 21 (black on white).
    """
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


class Palette(BaseModel):
    """The colours a theme applies."""

    background: str = Field(default="#ffffff")
    surface: str = Field(default="#f8fafc")
    text: str = Field(default="#111827")
    muted_text: str = Field(default="#6b7280")
    primary: str = Field(default="#1f2937")
    accent: str = Field(default="#2563eb")
    success: str = Field(default="#15803d")
    warning: str = Field(default="#b45309")
    danger: str = Field(default="#b91c1c")
    grid: str = Field(default="#e5e7eb")
    series: list[str] = Field(
        default_factory=lambda: [
            "#2563eb",
            "#15803d",
            "#b45309",
            "#b91c1c",
            "#7c3aed",
            "#0891b2",
        ]
    )
    """Categorical series colours, in assignment order.

    Six by default because a chart with more than six categories is
    already better served by grouping into "Other" than by adding a
    seventh colour nobody can distinguish.
    """

    @field_validator(
        "background",
        "surface",
        "text",
        "muted_text",
        "primary",
        "accent",
        "success",
        "warning",
        "danger",
        "grid",
    )
    @classmethod
    def _validate_colour(cls, value: str) -> str:
        parse_hex(value)
        return value

    @field_validator("series")
    @classmethod
    def _validate_series(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("A palette needs at least one series colour.")
        for value in values:
            parse_hex(value)
        return values


class Branding(BaseModel):
    """Corporate identity applied to a dashboard."""

    company_name: str = Field(default="AI-IOS", max_length=255)
    logo_data_uri: str | None = None
    """A ``data:`` URI rather than a URL.

    A dashboard that fetched a remote logo would depend on an external
    host being up, and would leak a request to that host on every load
    for every viewer.
    """

    footer_text: str | None = Field(default=None, max_length=512)


class Accessibility(BaseModel):
    """Accessibility options carried with the theme."""

    high_contrast: bool = False
    reduced_motion: bool = False
    minimum_font_px: int = Field(default=12, ge=8, le=32)
    colorblind_safe_series: bool = False


class ThemeDefinition(BaseModel):
    """A complete theme."""

    palette: Palette = Field(default_factory=Palette)
    branding: Branding = Field(default_factory=Branding)
    accessibility: Accessibility = Field(default_factory=Accessibility)


class ContrastFinding(BaseModel):
    """One text/background pair that falls below AA."""

    pair: str
    ratio: float
    required: float


def check_contrast(palette: Palette) -> list[ContrastFinding]:
    """Report text/background pairs below WCAG AA.

    Reported rather than rejected: a brand colour is sometimes fixed by
    forces outside engineering, and a visible, specific shortfall is
    more useful than a refusal that gets worked around by disabling the
    check.
    """
    checks = [
        ("text on background", palette.text, palette.background, WCAG_AA_NORMAL),
        ("text on surface", palette.text, palette.surface, WCAG_AA_NORMAL),
        ("muted text on background", palette.muted_text, palette.background, WCAG_AA_NORMAL),
        ("accent on background", palette.accent, palette.background, WCAG_AA_LARGE),
        ("danger on background", palette.danger, palette.background, WCAG_AA_LARGE),
    ]
    findings: list[ContrastFinding] = []
    for label, foreground, background, required in checks:
        ratio = contrast_ratio(foreground, background)
        if ratio < required:
            findings.append(ContrastFinding(pair=label, ratio=round(ratio, 2), required=required))
    return findings


DARK_PALETTE = Palette(
    background="#0b1220",
    surface="#111827",
    text="#f9fafb",
    muted_text="#9ca3af",
    primary="#e5e7eb",
    accent="#60a5fa",
    success="#4ade80",
    warning="#fbbf24",
    danger="#f87171",
    grid="#1f2937",
    series=["#60a5fa", "#4ade80", "#fbbf24", "#f87171", "#c084fc", "#22d3ee"],
)
"""The built-in dark palette.

Not the light palette inverted: inverting produces saturated colours
that vibrate against a dark background. These are the light hues
lightened and desaturated so they stay distinguishable and stay above
AA on ``#0b1220``.
"""


def parse_theme(raw: dict[str, Any]) -> ThemeDefinition:
    """Parse and validate a stored theme document."""
    return ThemeDefinition.model_validate(raw)


__all__ = [
    "DARK_PALETTE",
    "WCAG_AA_LARGE",
    "WCAG_AA_NORMAL",
    "Accessibility",
    "Branding",
    "ContrastFinding",
    "Palette",
    "ThemeDefinition",
    "check_contrast",
    "contrast_ratio",
    "parse_hex",
    "parse_theme",
    "relative_luminance",
]
