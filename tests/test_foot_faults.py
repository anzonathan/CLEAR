from src.faults.foot_faults import FootFaultJudge

def test_legal_near_end_serve():
    judge = FootFaultJudge(court_mode="singles")

    event = judge.evaluate(
        frame_idx=10,
        serving_end="near",
        left_foot_xy_m=(4.5, 24.2),
        right_foot_xy_m=(5.0, 24.3),
        service_motion_active=True,
        pre_contact=True,
    )

    assert event.status == "no_fault"


def test_near_baseline_violation():
    judge = FootFaultJudge(court_mode="singles")

    event = judge.evaluate(
        frame_idx=11,
        serving_end="near",
        left_foot_xy_m=(4.5, 23.76),
        right_foot_xy_m=(5.0, 24.3),
        service_motion_active=True,
        pre_contact=True,
    )

    assert event.status == "fault"
    assert "baseline" in event.reason.lower()


def test_missing_foot_is_uncertain():
    judge = FootFaultJudge()

    event = judge.evaluate(
        frame_idx=12,
        serving_end="near",
        left_foot_xy_m=(4.5, 24.2),
        right_foot_xy_m=None,
        service_motion_active=True,
        pre_contact=True,
    )

    assert event.status == "uncertain"
