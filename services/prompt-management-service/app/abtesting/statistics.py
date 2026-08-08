"""A/B experiment statistics (docs/061 "A/B TESTING": Statistical
Significance, Winner Selection).

**A genuine gap.** Nothing anywhere in this monorepo does hypothesis
testing -- confirmed by a repo-wide search for significance/p-value/
z-score machinery before writing this. SciPy is deliberately not a
dependency of this platform, so the normal CDF is computed from
:func:`math.erf`, which is exact to double precision and needs nothing
beyond the standard library.

The test is a **two-proportion z-test** on success rates. That is the
right test for the actual question here -- "did the variant convert a
larger *fraction* of its executions than the control?" -- where each
execution is an independent Bernoulli trial with a binary outcome.

**What this deliberately does not do.** It does not correct for
multiple comparisons across concurrent experiments, and it does not do
sequential testing. Both matter in a mature experimentation platform,
and both are wrong to fake: peeking at a fixed-horizon test repeatedly
inflates the false-positive rate, which is exactly why
:func:`evaluate_experiment` refuses to call a winner until both arms
reach their configured minimum sample size rather than reporting
significance the moment it first appears.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SAMPLES_PER_ARM = 2
"""A proportion needs at least two trials per arm to have a variance at
all. The configured ``minimum_samples_per_arm`` is normally far higher;
this is the floor below which the arithmetic itself is undefined."""


@dataclass(frozen=True, slots=True)
class ArmResult:
    """One experiment arm's own observed outcomes."""

    executions: int
    successes: int

    @property
    def rate(self) -> float:
        """Observed success rate, or ``0.0`` for an arm with no data."""
        return self.successes / self.executions if self.executions else 0.0


@dataclass(frozen=True, slots=True)
class SignificanceResult:
    """The verdict of one two-proportion z-test."""

    control_rate: float
    variant_rate: float
    difference: float
    z_score: float
    p_value: float
    significant: bool
    reason: str

    @property
    def variant_wins(self) -> bool:
        """Whether the variant is significantly *better*, not merely different.

        A significant result where the variant did worse is a real
        finding, but it is not a winner -- promoting it would ship a
        measured regression.
        """
        return self.significant and self.difference > 0


def normal_cdf(z: float) -> float:
    """The standard normal cumulative distribution at *z*.

    ``0.5 * (1 + erf(z / sqrt(2)))`` -- the exact closed form, not an
    approximation table.
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p_value(z: float) -> float:
    """The two-sided p-value for a z-statistic.

    Two-sided because the question is "do these arms differ?", not "is
    the variant better?" -- testing one-sided after seeing which arm
    led would double the effective false-positive rate.
    """
    return 2.0 * (1.0 - normal_cdf(abs(z)))


def two_proportion_z_test(control: ArmResult, variant: ArmResult) -> tuple[float, float]:
    """Return ``(z_score, p_value)`` for two observed proportions.

    Uses the pooled-variance form, which is the correct standard error
    under the null hypothesis that both arms share one true rate.

    Returns ``(0.0, 1.0)`` -- no evidence of any difference -- when the
    pooled variance is zero. That happens when every trial in both arms
    had the same outcome: 100% success or 100% failure everywhere gives
    genuinely no signal about which arm is better, and dividing by that
    zero would otherwise raise.
    """
    n1, n2 = control.executions, variant.executions
    if n1 < MIN_SAMPLES_PER_ARM or n2 < MIN_SAMPLES_PER_ARM:
        return 0.0, 1.0

    pooled = (control.successes + variant.successes) / (n1 + n2)
    variance = pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2)
    if variance <= 0.0:
        return 0.0, 1.0

    z = (variant.rate - control.rate) / math.sqrt(variance)
    return z, two_sided_p_value(z)


def evaluate_experiment(
    control: ArmResult,
    variant: ArmResult,
    *,
    minimum_samples_per_arm: int = 100,
    significance_level: float = 0.05,
) -> SignificanceResult:
    """Decide whether an experiment has reached a significant result.

    Refuses to call significance until **both** arms independently
    reach *minimum_samples_per_arm*. Checking a fixed-horizon test
    early and stopping as soon as it looks significant is the classic
    way to manufacture false positives; declining to answer before the
    horizon is the whole defence.
    """
    if control.executions < minimum_samples_per_arm:
        return _undecided(
            control,
            variant,
            f"The control arm has {control.executions} of the "
            f"{minimum_samples_per_arm} executions required.",
        )
    if variant.executions < minimum_samples_per_arm:
        return _undecided(
            control,
            variant,
            f"The variant arm has {variant.executions} of the "
            f"{minimum_samples_per_arm} executions required.",
        )

    z, p = two_proportion_z_test(control, variant)
    significant = p < significance_level
    if significant:
        better = "variant" if variant.rate > control.rate else "control"
        reason = (
            f"p={p:.4f} is below the {significance_level} threshold; "
            f"the {better} arm performed better."
        )
    else:
        reason = f"p={p:.4f} does not clear the {significance_level} threshold."

    return SignificanceResult(
        control_rate=control.rate,
        variant_rate=variant.rate,
        difference=variant.rate - control.rate,
        z_score=z,
        p_value=p,
        significant=significant,
        reason=reason,
    )


def _undecided(control: ArmResult, variant: ArmResult, reason: str) -> SignificanceResult:
    """A result that is explicitly not yet decidable."""
    return SignificanceResult(
        control_rate=control.rate,
        variant_rate=variant.rate,
        difference=variant.rate - control.rate,
        z_score=0.0,
        p_value=1.0,
        significant=False,
        reason=reason,
    )


def assign_arm(variant_weight: float, roll: float) -> bool:
    """Whether one execution routes to the variant ("Traffic Splitting").

    Takes the random draw as an argument rather than generating it, so
    routing is a pure, testable function: a caller passes
    ``random.random()`` in production and a fixed value in a test.

    Raises:
        ValueError: If *variant_weight* is outside ``[0, 1]``.
    """
    if not 0.0 <= variant_weight <= 1.0:
        raise ValueError(f"variant_weight must be within [0, 1], got {variant_weight!r}.")
    return roll < variant_weight


__all__ = [
    "MIN_SAMPLES_PER_ARM",
    "ArmResult",
    "SignificanceResult",
    "assign_arm",
    "evaluate_experiment",
    "normal_cdf",
    "two_proportion_z_test",
    "two_sided_p_value",
]
