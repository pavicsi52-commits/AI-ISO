"""Prompt template rendering (docs/061 "TEMPLATE MANAGEMENT").

**Rendering runs in Jinja2's ``SandboxedEnvironment``, and that is not
optional here.** A prompt template is user-authored content by
definition -- the entire point of this service is that prompts are
edited by people rather than embedded in application code. Unrestricted
Jinja2 can reach arbitrary Python attributes through any object placed
in its context, so an ordinary ``Environment`` over a user-editable
template is a real code-execution path, not a theoretical one. This is
the same call ``shared_core.notifications.renderer`` and
``ai-assistant-service/app/prompts/service.py`` each made for the same
reason.

**``StrictUndefined``, so a missing variable raises.** A prompt that
silently renders half its instructions because a variable was absent is
far worse than one that fails loudly: the model still answers, the
answer looks plausible, and nothing in the response says the
instructions were truncated.

Jinja2 gives docs/061's own "TEMPLATE MANAGEMENT" list natively --
Conditional Sections are ``{% if %}``, Inheritance is ``{% extends %}``,
Composition and Nested Templates and Shared Components are
``{% include %}``. What Jinja2 does *not* give, and this module adds,
is a bounded loader: templates resolve out of the database rather than
a filesystem, inheritance depth is capped, and a cyclic include chain
is refused rather than recursing until the stack dies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jinja2 import DictLoader, StrictUndefined, TemplateError, TemplateSyntaxError, meta
from jinja2.sandbox import SandboxedEnvironment

DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_RENDERED_LENGTH = 200_000


class TemplateRenderError(Exception):
    """A template could not be rendered.

    Its own exception rather than a bare ``ValueError`` so a caller can
    distinguish "the template is broken" from "the variables were
    wrong" without string-matching a message.
    """


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """One rendered prompt body and what producing it consumed."""

    body: str
    variables_used: tuple[str, ...] = ()
    depth: int = 1
    truncated: bool = False


@dataclass(slots=True)
class TemplateSource:
    """One template body available to a render, keyed by its own slug."""

    slug: str
    body: str
    parent_slug: str | None = None
    included_slugs: tuple[str, ...] = ()


@dataclass(slots=True)
class TemplateBundle:
    """Every template one render may reach, resolved up front.

    Resolved by the caller from the database *before* rendering starts,
    never lazily during it: a Jinja2 loader that hit the database
    mid-render would make a template able to trigger arbitrary queries
    by name, and would put I/O inside a synchronous render.
    """

    sources: dict[str, TemplateSource] = field(default_factory=dict)

    def add(self, source: TemplateSource) -> None:
        """Register one template body under its own slug."""
        self.sources[source.slug] = source

    def as_loader_mapping(self) -> dict[str, str]:
        """The ``{slug: body}`` mapping Jinja2's ``DictLoader`` wants."""
        return {slug: source.body for slug, source in self.sources.items()}


def _build_environment(bundle: TemplateBundle) -> SandboxedEnvironment:
    """A sandboxed environment that can only see *bundle*'s own templates."""
    return SandboxedEnvironment(
        loader=DictLoader(bundle.as_loader_mapping()),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def resolve_depth(bundle: TemplateBundle, slug: str, *, max_depth: int = DEFAULT_MAX_DEPTH) -> int:
    """How deep *slug*'s own inheritance/composition chain runs.

    Walks parents and includes breadth-first, refusing a chain that
    revisits a slug it has already seen. Detecting the cycle here, on a
    plain graph walk, is what keeps the actual render from recursing
    until the interpreter's own stack limit turns a bad template into a
    process crash.

    Raises:
        TemplateRenderError: If the chain cycles, exceeds *max_depth*,
            or references a slug the bundle has no body for.
    """
    if slug not in bundle.sources:
        raise TemplateRenderError(f"Template {slug!r} is not available to this render.")

    seen: set[str] = set()
    frontier = [slug]
    depth = 0
    while frontier:
        depth += 1
        if depth > max_depth:
            raise TemplateRenderError(
                f"Template {slug!r} nests deeper than the configured limit of {max_depth}."
            )
        next_frontier: list[str] = []
        for current in frontier:
            if current in seen:
                raise TemplateRenderError(
                    f"Template {slug!r} has a cyclic inheritance or include chain at {current!r}."
                )
            seen.add(current)
            source = bundle.sources.get(current)
            if source is None:
                raise TemplateRenderError(
                    f"Template {current!r} is referenced but not available to this render."
                )
            if source.parent_slug:
                next_frontier.append(source.parent_slug)
            next_frontier.extend(source.included_slugs)
        frontier = next_frontier
    return depth


def declared_variables(body: str) -> tuple[str, ...]:
    """Every undeclared name *body* references, sorted.

    Uses Jinja2's own parser via ``meta.find_undeclared_variables``
    rather than a regex, so ``{% for row in rows %}{{ row.x }}{% endfor %}``
    correctly reports ``rows`` and not ``row``.

    Raises:
        TemplateRenderError: If *body* is not valid Jinja2.
    """
    environment = SandboxedEnvironment(undefined=StrictUndefined)
    try:
        parsed = environment.parse(body)
    except TemplateSyntaxError as exc:
        raise TemplateRenderError(
            f"Template syntax error on line {exc.lineno}: {exc.message}"
        ) from exc
    return tuple(sorted(meta.find_undeclared_variables(parsed)))


def validate_syntax(body: str) -> str | None:
    """Return a syntax error message for *body*, or ``None`` if valid.

    The non-raising counterpart to :func:`declared_variables`, for the
    security scanner and the draft-save path, where an invalid template
    is a finding to record rather than an exception to propagate.
    """
    try:
        declared_variables(body)
    except TemplateRenderError as exc:
        return str(exc)
    return None


def render(
    bundle: TemplateBundle,
    slug: str,
    variables: dict[str, Any],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_length: int = DEFAULT_MAX_RENDERED_LENGTH,
) -> RenderedPrompt:
    """Render *slug* from *bundle* against *variables*.

    Raises:
        TemplateRenderError: If the chain cycles or is too deep, the
            template's syntax is invalid, a required variable is
            missing, or the rendered body exceeds *max_length*.
    """
    depth = resolve_depth(bundle, slug, max_depth=max_depth)
    environment = _build_environment(bundle)

    try:
        template = environment.get_template(slug)
        body = template.render(**variables)
    except TemplateSyntaxError as exc:
        raise TemplateRenderError(
            f"Template syntax error on line {exc.lineno}: {exc.message}"
        ) from exc
    except TemplateError as exc:
        # Covers UndefinedError from StrictUndefined, which is the
        # common case: a declared variable the caller did not supply.
        raise TemplateRenderError(f"Template {slug!r} could not be rendered: {exc}") from exc
    except RecursionError as exc:
        # Belt and braces: resolve_depth already refuses cyclic chains,
        # but a self-recursive macro is a shape that walk cannot see.
        raise TemplateRenderError(f"Template {slug!r} recursed without terminating.") from exc

    if len(body) > max_length:
        raise TemplateRenderError(
            f"Template {slug!r} rendered {len(body)} characters, over the "
            f"{max_length} limit. A runaway loop is the usual cause."
        )

    source = bundle.sources[slug]
    return RenderedPrompt(body=body, variables_used=declared_variables(source.body), depth=depth)


def render_body(
    body: str,
    variables: dict[str, Any],
    *,
    max_length: int = DEFAULT_MAX_RENDERED_LENGTH,
) -> RenderedPrompt:
    """Render one standalone body with no inheritance or includes.

    The common path: most prompt versions are a single template with no
    parent, and going through :class:`TemplateBundle` for them would be
    ceremony with no benefit.

    Raises:
        TemplateRenderError: If the syntax is invalid, a required
            variable is missing, or the result exceeds *max_length*.
    """
    bundle = TemplateBundle()
    bundle.add(TemplateSource(slug="__inline__", body=body))
    return render(bundle, "__inline__", variables, max_depth=1, max_length=max_length)


__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_RENDERED_LENGTH",
    "RenderedPrompt",
    "TemplateBundle",
    "TemplateRenderError",
    "TemplateSource",
    "declared_variables",
    "render",
    "render_body",
    "resolve_depth",
    "validate_syntax",
]
