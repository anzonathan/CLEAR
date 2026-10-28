"""Rule-based tennis service-fault judge using court-plane bounce coordinates."""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from src.calibration.court_geometry import SPEC, evaluate_court_point
from src.faults.fault_events import FaultEvent

Point = Tuple[float, float]
ServingEnd = Literal["far", "near"]
ServiceSide = Literal["left", "right"]
CourtMode = Literal["singles", "doubles"]


def _service_mode(serving_end: ServingEnd, service_side: ServiceSide) -> str:
    """Map server end + side to the diagonal target service-box mode."""
    # Server near → ball must land in far box (opponent end)
    # Server far  → ball must land in near box
    # Tennis: serve to the diagonal box (right-side serve → receiver's deuce/ad mapping)
    if serving_end == "near":
        # Near server, service_side "right" → far-left box from shared coords
        # (receiver faces server; diagonal is opposite lateral half)
        return "service_far_left" if service_side == "right" else "service_far_right"
    return "service_near_left" if service_side == "right" else "service_near_right"


class ServiceFaultJudge:
    """Evaluate whether a serve bounce is a service fault (or let)."""

    def __init__(self, court_mode: CourtMode = "singles") -> None:
        if court_mode not in ("singles", "doubles"):
            raise ValueError("court_mode must be 'singles' or 'doubles'")
        self.court_mode = court_mode

    def evaluate(
        self,
        frame_idx: int,
        bounce_xy_m: Optional[Point],
        *,
        serving_end: ServingEnd,
        service_side: ServiceSide,
        is_serve: bool,
        net_cord: bool = False,
        player_id: Optional[int] = None,
        observation_confidence: float = 1.0,
        doubt_zone_cm: float = 15.0,
        reproj_uncertainty_cm: float = 3.5,
    ) -> FaultEvent:
        """Judge one serve bounce against the correct service box.

        net_cord + in box → let (status no_fault with reason, fault_type let)
        bounce outside box → service_fault
        """
        if frame_idx < 0:
            raise ValueError("frame_idx cannot be negative")
        if not 0.0 <= observation_confidence <= 1.0:
            raise ValueError("observation_confidence must be between 0 and 1")

        if not is_serve:
            return FaultEvent(
                fault_type="service_fault",
                status="uncertain",
                frame_idx=frame_idx,
                reason="Not a serve point",
                confidence=observation_confidence,
                player_id=player_id,
            )

        if bounce_xy_m is None or observation_confidence < 0.60:
            return FaultEvent(
                fault_type="service_fault",
                status="uncertain",
                frame_idx=frame_idx,
                reason="Serve bounce observation missing or low confidence",
                confidence=observation_confidence,
                player_id=player_id,
            )

        mode = _service_mode(serving_end, service_side)
        x_m, y_m = float(bounce_xy_m[0]), float(bounce_xy_m[1])

        # target_half is implied by service_* modes in evaluate_court_point
        res = evaluate_court_point(
            x_m=x_m,
            y_m=y_m,
            mode=mode,  # type: ignore[arg-type]
            target_half="full",
            doubt_zone_cm=doubt_zone_cm,
            reproj_uncertainty_cm=reproj_uncertainty_cm,
        )

        conf = min(observation_confidence, float(res["confidence"]))

        if res["is_in"]:
            if net_cord:
                return FaultEvent(
                    fault_type="let",
                    status="no_fault",
                    frame_idx=frame_idx,
                    reason=f"Let: net cord and bounce in service box ({mode})",
                    confidence=conf,
                    player_id=player_id,
                )
            return FaultEvent(
                fault_type="service_fault",
                status="no_fault",
                frame_idx=frame_idx,
                reason=f"Serve in correct box ({mode}), margin {res['signed_margin_cm']} cm",
                confidence=conf,
                player_id=player_id,
            )

        return FaultEvent(
            fault_type="service_fault",
            status="fault",
            frame_idx=frame_idx,
            reason=(
                f"Service fault: bounce outside {mode} "
                f"(closest {res['closest_line']}, margin {res['signed_margin_cm']} cm)"
            ),
            confidence=conf,
            player_id=player_id,
        )