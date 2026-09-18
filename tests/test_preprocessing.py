"""Automated tests for the Week 2 elephant GPS preprocessing functions."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from preprocessing import (  # noqa: E402
    GAP_THRESHOLD_MINUTES,
    add_movement_metrics,
    haversine_m,
    screen_spike_candidates,
    segment_trajectories,
)


def test_haversine_same_point_is_zero() -> None:
    distance = haversine_m(-18.95, 34.50, -18.95, 34.50)
    assert np.isclose(distance, 0.0)


def test_haversine_one_degree_at_equator() -> None:
    distance = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert np.isclose(distance, 111_195.0, atol=20.0)


def test_gap_above_30_minutes_starts_new_segment() -> None:
    data = pd.DataFrame(
        {
            "AnimalID": ["A", "A", "A", "A"],
            "Timestamp": pd.to_datetime(
                [
                    "2026-01-01 00:00",
                    "2026-01-01 00:15",
                    "2026-01-01 00:45",
                    "2026-01-01 01:16",
                ]
            ),
            "Latitude": [-19.0, -19.0, -19.0, -19.0],
            "Longitude": [34.0, 34.001, 34.002, 34.003],
        }
    )
    segmented = segment_trajectories(data)

    assert GAP_THRESHOLD_MINUTES == 30.0
    assert segmented["SegmentNumber"].tolist() == [1, 1, 1, 2]
    assert segmented["SegmentStart"].tolist() == [True, False, False, True]


def test_jump_and_return_screen_flags_middle_point() -> None:
    data = pd.DataFrame(
        {
            "AnimalID": ["A", "A", "A"],
            "Timestamp": pd.to_datetime(
                ["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 00:30"]
            ),
            "Latitude": [-19.0, -18.94, -19.0],
            "Longitude": [34.0, 34.0, 34.0001],
        }
    )
    candidates = screen_spike_candidates(data)

    assert len(candidates) == 1
    assert candidates.iloc[0]["Timestamp"] == pd.Timestamp("2026-01-01 00:15")
    assert candidates.iloc[0]["IncomingSpeed_mps"] > 5.0
    assert candidates.iloc[0]["OutgoingSpeed_mps"] > 5.0


def test_no_movement_is_calculated_across_segment_boundary() -> None:
    data = pd.DataFrame(
        {
            "AnimalID": ["A", "A", "A"],
            "Timestamp": pd.to_datetime(
                ["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 01:00"]
            ),
            "Latitude": [-19.0, -19.0001, -19.01],
            "Longitude": [34.0, 34.0001, 34.01],
        }
    )
    segmented = segment_trajectories(data)
    measured = add_movement_metrics(segmented)

    assert measured.loc[2, "SegmentStart"]
    assert pd.isna(measured.loc[2, "StepTime_s"])
    assert pd.isna(measured.loc[2, "StepDistance_m"])
    assert pd.isna(measured.loc[2, "Speed_mps"])
