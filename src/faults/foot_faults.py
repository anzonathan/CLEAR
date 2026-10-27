"""Rule-based tennis foot-fault judge using court-plane coordinates.

Coordinates follow src/calibration/court_geometry.py:
    x: 0.0 .. 10.97 metres, left to right
    y: 0.0 .. 23.77 metres, far baseline to near baseline

Each foot point must represent the estimated court-plane contact position
of that foot, not the player's bounding-box centre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from src.calibration.court_geometry import SPEC
from src.faults.fault_events import FaultEvent


Point = Tuple[float, float]
ServingEnd = Literal["far", "near"]
CourtMode = Literal["singles", "doubles"]
ServiceSide = Literal["left", "right"]


@dataclass(frozen=True)
class FootFaultResult:
    """Detailed geometric result for one foot."""

    foot: str
    is_fault: bool
    reason: str
    x_m: float
    y_m: float


class FootFaultJudge:
    """Evaluate server foot placement during the pre-contact service motion."""

    def __init__(
        self,
        court_mode: CourtMode = "singles",
        position_tolerance_m: float = 0.0,
    ) -> None:
        if court_mode not in ("singles", "doubles"):
            raise ValueError("court_mode must be 'singles' or 'doubles'")

        if position_tolerance_m < 0:
            raise ValueError("position_tolerance_m cannot be negative")

        self.court_mode = court_mode
        self.position_tolerance_m = float(position_tolerance_m)

    def _court_bounds(self) -> tuple[float, float]:
        if self.court_mode == "singles":
            return SPEC.alley_width_m, (
                SPEC.doubles_width_m - SPEC.alley_width_m
            )
        return 0.0, SPEC.doubles_width_m

    def evaluate_foot(
        self,
        foot_name: str,
        foot_xy_m: Point,
        serving_end: ServingEnd,
        service_side: Optional[ServiceSide] = None,
    ) -> FootFaultResult:
        """Check one foot against the relevant serving-end boundaries.

        service_side is optional and refers to the left/right half in the
        shared court coordinate system, not the server's anatomical left/right.
        """
        x, y = float(foot_xy_m[0]), float(foot_xy_m[1])

        if serving_end not in ("far", "near"):
            raise ValueError("serving_end must be 'far' or 'near'")

        if service_side not in (None, "left", "right"):
            raise ValueError("service_side must be 'left', 'right', or None")

        if not all(map(lambda v: abs(v) < float("inf"), (x, y))):
            return FootFaultResult(
                foot_name, True, "Invalid foot coordinates", x, y
            )

        x_min, x_max = self._court_bounds()

        # A foot must remain outside the court, behind the serving baseline.
        # Include half the painted baseline width because touching the line
        # itself is a foot fault.
        baseline_y = 0.0 if serving_end == "far" else SPEC.length_m
        baseline_half_width = SPEC.line_width_m / 2.0
        tol = self.position_tolerance_m

        if serving_end == "far":
            baseline_violation = y >= baseline_y - baseline_half_width - tol
        else:
            baseline_violation = y <= baseline_y + baseline_half_width + tol

        if baseline_violation:
            return FootFaultResult(
                foot_name,
                True,
                "Foot touches or crosses the serving baseline",
                x,
                y,
            )

        # Check the imaginary extensions of the applicable sidelines.
        # This checks the estimated foot contact point; the full foot
        # footprint must be considered by a future vision-based adapter.
        if x <= x_min + tol:
            return FootFaultResult(
                foot_name, True, "Foot touches or crosses the left sideline extension",
                x, y
            )

        if x >= x_max - tol:
            return FootFaultResult(
                foot_name, True, "Foot touches or crosses the right sideline extension",
                x, y
            )

        # A server must remain on the correct side of the centre-mark
        # extension during the relevant service motion.
        if service_side is not None:
            centre_x = SPEC.center_x_m

            if service_side == "left" and x >= centre_x - tol:
                return FootFaultResult(
                    foot_name, True,
                    "Foot crosses or touches the centre-mark extension",
                    x, y
                )

            if service_side == "right" and x <= centre_x + tol:
                return FootFaultResult(
                    foot_name, True,
                    "Foot crosses or touches the centre-mark extension",
                    x, y
                )

        return FootFaultResult(
            foot_name, False, "No geometric foot fault detected", x, y
        )

    def evaluate(
        self,
        frame_idx: int,
        serving_end: ServingEnd,
        left_foot_xy_m: Optional[Point],
        right_foot_xy_m: Optional[Point],
        *,
        service_motion_active: bool,
        pre_contact: bool,
        service_side: Optional[ServiceSide] = None,
        player_id: Optional[int] = None,
        observation_confidence: float = 1.0,
    ) -> FaultEvent:
        """Evaluate both feet and produce a shared FaultEvent.

        Missing feet or unreliable observations produce 'uncertain', not
        an assumed legal serve. This judge does not modify the score.
        """
        if frame_idx < 0:
            raise ValueError("frame_idx cannot be negative")

        if not 0.0 <= observation_confidence <= 1.0:
            raise ValueError("observation_confidence must be between 0 and 1")

        if not service_motion_active or not pre_contact:
            return FaultEvent(
                fault_type="foot_fault",
                status="uncertain",
                frame_idx=frame_idx,
                reason="Frame is outside the evaluable pre-contact service motion",
                confidence=observation_confidence,
                player_id=player_id,
            )

        if (
            left_foot_xy_m is None
            or right_foot_xy_m is None
            or observation_confidence < 0.60
        ):
            return FaultEvent(
                fault_type="foot_fault",
                status="uncertain",
                frame_idx=frame_idx,
                reason="Both feet and reliable position observations are required",
                confidence=observation_confidence,
                player_id=player_id,
            )

        results = [
            self.evaluate_foot(
                "left_foot", left_foot_xy_m, serving_end, service_side
            ),
            self.evaluate_foot(
                "right_foot", right_foot_xy_m, serving_end, service_side
            ),
        ]

        violations = [r for r in results if r.is_fault]

        if violations:
            reasons = "; ".join(
                f"{r.foot}: {r.reason}" for r in violations
            )
            return FaultEvent(
                fault_type="foot_fault",
                status="fault",
                frame_idx=frame_idx,
                reason=reasons,
                confidence=observation_confidence,
                player_id=player_id,
            )

        return FaultEvent(
            fault_type="foot_fault",
            status="no_fault",
            frame_idx=frame_idx,
            reason="Neither foot violates the checked serving boundaries",
            confidence=observation_confidence,
            player_id=player_id,
        )
