"""Cross-checking the two engines against each other.

Every conversion this program performs is computed twice - once by the rigorous
Lambert equations of manual section 3.1, once by the polynomial coefficient
method of section 3.4 - and the two results must agree.

The two are never averaged and the polynomial result is never substituted for
the rigorous one. Disagreement is a defect, and a defect that reaches a sealed
survey is the failure this program exists to prevent. It is reported, named, and
refused.

Tolerance: **0.5 mm**, which is the accuracy NGS states it fit the Appendix C
polynomial coefficients to (manual PDF p. 54: "the fewest number of coefficients
possible that provided 0.5 mm coordinate accuracy in the conversion"). Holding
the two engines to the published accuracy of the weaker one is the tightest
bound the sources support.

Where the two legitimately diverge: outside the latitude band a zone's
polynomial was fit to. That happens routinely in this program, because
converting a point from one Michigan zone into another evaluates the target
zone's polynomial away from home. ``compare`` reports the discrepancy and lets
the caller decide - the pipeline treats an out-of-band point as a warning
carrying the measured discrepancy, and an in-band point as an error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# NGS's stated fitting accuracy for the Appendix C coefficients.
# Manual section 3.4, PDF p. 54.
AGREEMENT_TOLERANCE_M = 0.0005


class EngineDisagreementError(Exception):
    """The two computation engines produced materially different answers.

    Fails closed. One of them is wrong and this program cannot tell which, so
    it refuses to emit a coordinate rather than pick one.
    """


@dataclass(frozen=True)
class Agreement:
    """How closely the two engines agreed on one point."""

    northing_difference: float
    """Meters, rigorous minus polynomial."""

    easting_difference: float
    """Meters, rigorous minus polynomial."""

    @property
    def distance(self) -> float:
        """Straight-line separation of the two computed positions, meters."""
        return math.hypot(self.northing_difference, self.easting_difference)

    @property
    def within_tolerance(self) -> bool:
        return self.distance <= AGREEMENT_TOLERANCE_M

    def describe(self) -> str:
        return (
            f"{self.distance * 1000.0:.4f} mm "
            f"(dN {self.northing_difference * 1000.0:+.4f} mm, "
            f"dE {self.easting_difference * 1000.0:+.4f} mm)"
        )


def compare(rigorous, polynomial) -> Agreement:
    """Measure the separation between two GridPoint results."""
    return Agreement(
        northing_difference=rigorous.northing - polynomial.northing,
        easting_difference=rigorous.easting - polynomial.easting,
    )


def require_agreement(agreement: Agreement, context: str) -> None:
    """Refuse if the engines disagree beyond tolerance.

    ``context`` names the point, so the refusal identifies the offending item
    rather than merely reporting that something went wrong.
    """
    if agreement.within_tolerance:
        return
    raise EngineDisagreementError(
        f"{context}: the two independent computation engines disagree by "
        f"{agreement.describe()}, which exceeds the "
        f"{AGREEMENT_TOLERANCE_M * 1000.0:.1f} mm tolerance. The rigorous "
        f"Lambert equations (manual section 3.1) and the polynomial "
        f"coefficient method (section 3.4) should agree to within the accuracy "
        f"NGS fitted the coefficients to. One of them is wrong for this point "
        f"and this program cannot determine which, so no coordinate is "
        f"produced."
    )
