"""Seed Framework.

Per docs/018_Enterprise_Database_Framework.md.txt "SEED FRAMEWORK":
Development Seed, Testing Seed, Demo Seed, Factory Support, Fixture
Support. This module provides the registry and runner every service uses
to organize its own seed functions by environment; no concrete seed data
lives here -- that would mean creating business tables/logic, which this
framework must not do (docs/018 "DO NOT IMPLEMENT"). "Factory Support" is
:mod:`shared_core.database.fixtures`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.database.seed")


class SeedEnvironment(StrEnum):
    """Which deployment context a seed is meant to run in."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    DEMO = "demo"


SeedFunc = Callable[[AsyncSession], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class SeedDefinition:
    """One registered seed: a name, its target environment, and its runner."""

    name: str
    environment: SeedEnvironment
    run: SeedFunc
    order: int = 0


class SeedRegistry:
    """Registry of seed functions, executed per-environment in ``order``.

    Usage::

        registry = SeedRegistry()

        @seed(registry, "default_roles", SeedEnvironment.DEVELOPMENT)
        async def _seed_default_roles(session: AsyncSession) -> None:
            ...

        await registry.run(session, SeedEnvironment.DEVELOPMENT)
    """

    def __init__(self) -> None:
        self._seeds: list[SeedDefinition] = []

    def register(
        self,
        name: str,
        environment: SeedEnvironment,
        run: SeedFunc,
        *,
        order: int = 0,
    ) -> None:
        """Register *run* as a named seed for *environment*.

        Raises:
            ValueError: If a seed with the same name is already registered
                for that environment.
        """
        if any(s.name == name and s.environment == environment for s in self._seeds):
            raise ValueError(f"A seed named {name!r} is already registered for {environment!r}.")
        self._seeds.append(SeedDefinition(name=name, environment=environment, run=run, order=order))

    def seeds_for(self, environment: SeedEnvironment) -> list[SeedDefinition]:
        """Return every seed registered for *environment*, in run order."""
        return sorted(
            (s for s in self._seeds if s.environment == environment), key=lambda s: s.order
        )

    async def run(self, session: AsyncSession, environment: SeedEnvironment) -> list[str]:
        """Run every seed registered for *environment*, in order, and commit.

        Returns the names of the seeds that ran, in execution order.
        """
        executed: list[str] = []
        for seed_def in self.seeds_for(environment):
            logger.info(
                "running seed",
                extra={"extra_fields": {"seed": seed_def.name, "environment": environment.value}},
            )
            await seed_def.run(session)
            executed.append(seed_def.name)
        await session.commit()
        return executed


def seed(
    registry: SeedRegistry, name: str, environment: SeedEnvironment, *, order: int = 0
) -> Callable[[SeedFunc], SeedFunc]:
    """Decorator form of :meth:`SeedRegistry.register`."""

    def decorator(func: SeedFunc) -> SeedFunc:
        registry.register(name, environment, func, order=order)
        return func

    return decorator


__all__ = ["SeedDefinition", "SeedEnvironment", "SeedRegistry", "seed"]
