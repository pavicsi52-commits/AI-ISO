"""Theme management ("THEMES", "ACCESSIBILITY").

Themes are validated on write by :mod:`app.themes.schema`, so a palette
that would render unreadable text is refused at authoring time rather
than discovered by whoever opens the dashboard. Contrast shortfalls are
*reported* alongside the saved theme rather than rejected -- a brand
colour is sometimes fixed by forces outside engineering, and a visible,
specific shortfall is more useful than a refusal that gets worked
around by disabling the check.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.dashboard_theme import DashboardTheme
from app.models.enums import ThemeMode
from app.repositories.dashboard_theme import DashboardThemeRepository
from app.themes.schema import (
    DARK_PALETTE,
    ContrastFinding,
    Palette,
    ThemeDefinition,
    check_contrast,
    parse_theme,
)

SYSTEM_THEMES: dict[str, tuple[str, ThemeMode, Palette]] = {
    "aiios-light": ("AI-IOS Light", ThemeMode.LIGHT, Palette()),
    "aiios-dark": ("AI-IOS Dark", ThemeMode.DARK, DARK_PALETTE),
}
"""The built-in themes every organization starts with.

Seeded rather than hard-coded into the renderer so an organization can
copy one and adjust it, which is what people actually want from a
"default theme" the moment they have a logo.
"""


def mode_of(theme: DashboardTheme) -> ThemeMode:
    """A theme's mode as a genuine enum member.

    ``mode`` is annotated ``Mapped[ThemeMode]`` but stored in a
    ``String``, so a row loaded from Postgres yields a raw ``str``.
    """
    value = theme.mode
    return value if isinstance(value, ThemeMode) else ThemeMode(value)


class ThemeService:
    """Creates, validates, and serves dashboard themes."""

    def __init__(self, themes: DashboardThemeRepository) -> None:
        self._themes = themes

    async def list_for_org(self, organization_id: UUID) -> list[DashboardTheme]:
        """Every theme available to an organization."""
        return await self._themes.list_for_org(organization_id)

    async def get_by_id(self, theme_id: UUID) -> DashboardTheme:
        """Return one theme.

        Raises:
            NotFoundError: If no such theme exists.
        """
        return await self._themes.require_by_id(theme_id)

    async def get_by_slug(self, organization_id: UUID, slug: str) -> DashboardTheme | None:
        """Return the theme registered under *slug*, if any."""
        return await self._themes.get_by_slug(organization_id, slug)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        slug: str,
        name: str,
        description: str | None = None,
        mode: ThemeMode = ThemeMode.LIGHT,
        definition: dict[str, Any] | None = None,
        is_system: bool = False,
    ) -> tuple[DashboardTheme, list[ContrastFinding]]:
        """Create a theme, returning it with any contrast shortfalls.

        Raises:
            ConflictError: If the slug is already used.
            ValidationError: If the definition is malformed.
        """
        if await self._themes.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"A theme with slug {slug!r} already exists.")
        parsed = self._parse(definition or {})
        theme = await self._themes.create(
            DashboardTheme(
                organization_id=organization_id,
                project_id=project_id,
                slug=slug,
                name=name,
                description=description,
                mode=mode,
                palette=parsed.palette.model_dump(mode="json"),
                branding=parsed.branding.model_dump(mode="json"),
                accessibility=parsed.accessibility.model_dump(mode="json"),
                is_system=is_system,
            )
        )
        return theme, check_contrast(parsed.palette)

    async def update(
        self,
        theme_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        mode: ThemeMode | None = None,
        definition: dict[str, Any] | None = None,
    ) -> tuple[DashboardTheme, list[ContrastFinding]]:
        """Update a theme in place.

        Raises:
            NotFoundError: If no such theme exists.
            ConflictError: If it is a built-in system theme.
            ValidationError: If the definition is malformed.
        """
        theme = await self._themes.require_by_id(theme_id)
        if theme.is_system:
            raise ConflictError(
                "Built-in themes cannot be edited; copy one and change the copy instead."
            )
        if name is not None:
            theme.name = name
        if description is not None:
            theme.description = description
        if mode is not None:
            theme.mode = mode

        parsed = self._parse(definition) if definition is not None else self.definition_of(theme)
        if definition is not None:
            theme.palette = parsed.palette.model_dump(mode="json")
            theme.branding = parsed.branding.model_dump(mode="json")
            theme.accessibility = parsed.accessibility.model_dump(mode="json")

        updated = await self._themes.update(theme)
        return updated, check_contrast(parsed.palette)

    async def delete(self, theme_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-delete a theme.

        Raises:
            NotFoundError: If no such theme exists.
            ConflictError: If it is a built-in system theme.
        """
        theme = await self._themes.require_by_id(theme_id)
        if theme.is_system:
            raise ConflictError("Built-in themes cannot be deleted.")
        await self._themes.delete(theme_id, deleted_by=deleted_by)

    async def seed_system_themes(self, organization_id: UUID) -> list[DashboardTheme]:
        """Ensure the built-in themes exist, returning those created.

        Idempotent: re-running it after a deployment adds nothing, which
        is what lets it be called from startup without a guard.
        """
        created: list[DashboardTheme] = []
        for slug, (name, mode, palette) in SYSTEM_THEMES.items():
            if await self._themes.get_by_slug(organization_id, slug) is not None:
                continue
            theme, _findings = await self.create(
                organization_id=organization_id,
                slug=slug,
                name=name,
                mode=mode,
                definition={"palette": palette.model_dump(mode="json")},
                is_system=True,
            )
            created.append(theme)
        return created

    def definition_of(self, theme: DashboardTheme) -> ThemeDefinition:
        """Reassemble a stored theme into its validated document."""
        return self._parse(
            {
                "palette": theme.palette or {},
                "branding": theme.branding or {},
                "accessibility": theme.accessibility or {},
            }
        )

    def audit(self, theme: DashboardTheme) -> dict[str, Any]:
        """Report a stored theme's accessibility standing.

        Reported per pair, so "this theme fails AA" comes with which
        pair and by how much rather than a bare verdict nobody can act
        on.
        """
        parsed = self.definition_of(theme)
        findings = check_contrast(parsed.palette)
        return {
            "theme_id": str(theme.id),
            "slug": theme.slug,
            "mode": str(mode_of(theme)),
            "wcag_aa": not findings,
            "findings": [finding.model_dump() for finding in findings],
            "high_contrast": parsed.accessibility.high_contrast,
            "reduced_motion": parsed.accessibility.reduced_motion,
            "minimum_font_px": parsed.accessibility.minimum_font_px,
        }

    @staticmethod
    def _parse(raw: dict[str, Any]) -> ThemeDefinition:
        """Parse a theme document, raising the platform's own error."""
        try:
            return parse_theme(raw)
        except Exception as exc:
            raise ValidationError(f"Invalid theme definition: {exc}") from exc


__all__ = ["SYSTEM_THEMES", "ThemeService", "mode_of"]
