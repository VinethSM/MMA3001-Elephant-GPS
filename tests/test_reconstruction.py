import numpy as np
import pandas as pd
import pytest

from src import reconstruction


def sample_segment(n=9):
    """Create a simple straight-line test trajectory."""

    timestamp = pd.date_range(
        "2020-01-01",
        periods=n,
        freq="15min",
    )

    x = (
        np.arange(n, dtype=float)
        * 100.0
    )

    y = (
        np.arange(n, dtype=float)
        * 50.0
    )

    latitude, longitude = (
        reconstruction.local_xy_to_latlon(
            x,
            y,
            -19.0,
            34.0,
        )
    )

    return pd.DataFrame(
        {
            "SourceRowNumber": np.arange(
                2,
                n + 2,
            ),
            "AnimalID": "test-elephant",
            "SegmentID": "test-elephant_S001",
            "Timestamp": timestamp,
            "Latitude": latitude,
            "Longitude": longitude,
            "ElapsedSegment_min": (
                np.arange(n) * 15.0
            ),
            "LocalX_m": x,
            "LocalY_m": y,
        }
    )


def test_interval_to_stride():
    assert (
        reconstruction.interval_to_stride(30)
        == 2
    )

    assert (
        reconstruction.interval_to_stride(240)
        == 16
    )

    with pytest.raises(
        ValueError,
        match="Unsupported interval",
    ):
        reconstruction.interval_to_stride(45)


def test_mask_does_not_allow_extrapolation():
    mask = (
        reconstruction.make_downsampling_mask(
            sample_segment(),
            60,
            1,
        )
    )

    retained_positions = mask.loc[
        mask["Retained"],
        "PositionInSegment",
    ].tolist()

    eligible_positions = mask.loc[
        mask["EligibleWithheld"],
        "PositionInSegment",
    ].tolist()

    assert retained_positions == [1, 5]
    assert eligible_positions == [2, 3, 4]

    assert (
        mask.loc[0, "MaskReason"]
        == "before_first_anchor"
    )

    assert (
        mask.loc[8, "MaskReason"]
        == "after_last_anchor"
    )


def test_linear_reproduces_straight_line():
    anchor_time = np.array(
        [0.0, 30.0, 60.0]
    )

    anchor_x = (
        2.0 * anchor_time + 10.0
    )

    anchor_y = (
        -3.0 * anchor_time + 5.0
    )

    query_time = np.array(
        [15.0, 45.0]
    )

    x, y = reconstruction.interpolate_xy(
        anchor_time,
        anchor_x,
        anchor_y,
        query_time,
        "linear",
    )

    np.testing.assert_allclose(
        x,
        2.0 * query_time + 10.0,
    )

    np.testing.assert_allclose(
        y,
        -3.0 * query_time + 5.0,
    )


def test_interpolation_refuses_extrapolation():
    with pytest.raises(
        ValueError,
        match="no extrapolation",
    ):
        reconstruction.interpolate_xy(
            [0.0, 60.0],
            [0.0, 60.0],
            [0.0, 60.0],
            [90.0],
            "linear",
        )


def test_cubic_requires_four_anchors():
    with pytest.raises(
        ValueError,
        match="at least 4",
    ):
        reconstruction.interpolate_xy(
            [0.0, 30.0, 60.0],
            [0.0, 30.0, 60.0],
            [0.0, 30.0, 60.0],
            [15.0],
            "cubic",
        )


def test_local_coordinate_round_trip():
    original_x = np.array(
        [0.0, 100.0, -250.0]
    )

    original_y = np.array(
        [0.0, -80.0, 400.0]
    )

    latitude, longitude = (
        reconstruction.local_xy_to_latlon(
            original_x,
            original_y,
            -19.0,
            34.0,
        )
    )

    recreated_x = (
        reconstruction.EARTH_RADIUS_M
        * np.radians(
            longitude - 34.0
        )
        * np.cos(
            np.radians(-19.0)
        )
    )

    recreated_y = (
        reconstruction.EARTH_RADIUS_M
        * np.radians(
            latitude + 19.0
        )
    )

    np.testing.assert_allclose(
        recreated_x,
        original_x,
        atol=1e-8,
    )

    np.testing.assert_allclose(
        recreated_y,
        original_y,
        atol=1e-8,
    )


def test_reconstruction_is_deterministic():
    reference = sample_segment(17)

    first, first_case = (
        reconstruction.reconstruct_case(
            reference,
            "test-elephant_S001",
            60,
            0,
            "linear",
        )
    )

    second, second_case = (
        reconstruction.reconstruct_case(
            reference,
            "test-elephant_S001",
            60,
            0,
            "linear",
        )
    )

    np.testing.assert_allclose(
        first["EstimatedX_m"],
        second["EstimatedX_m"],
    )

    np.testing.assert_allclose(
        first["EstimatedY_m"],
        second["EstimatedY_m"],
    )

    assert first_case["Status"] == "ok"
    assert second_case["Status"] == "ok"

    assert (
        first["PositionError_m"].max()
        < 1e-6
    )