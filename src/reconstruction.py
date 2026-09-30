"""Downsample and reconstruct cleaned elephant GPS trajectories.

Week 3 of the MMA3001 elephant GPS sampling project. Interpolation is
performed only inside a continuous Week 2 segment and never extrapolates.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import yaml
from scipy.interpolate import CubicSpline, PchipInterpolator


EARTH_RADIUS_M = 6_371_000.0
BASE_INTERVAL_MINUTES = 15
SUPPORTED_INTERVALS = (30, 60, 120, 240)
SUPPORTED_METHODS = ("linear", "cubic", "pchip")
MINIMUM_ANCHORS = {
    "linear": 2,
    "cubic": 4,
    "pchip": 2,
}

REQUIRED_REFERENCE_COLUMNS = [
    "SourceRowNumber",
    "AnimalID",
    "Timestamp",
    "Latitude",
    "Longitude",
    "SegmentID",
    "ElapsedSegment_min",
    "LocalX_m",
    "LocalY_m",
]


def find_project_root(start: Path | None = None) -> Path:
    """Return the project folder containing data and src."""

    first = Path(start).resolve() if start is not None else Path.cwd().resolve()

    for folder in [first, *first.parents]:
        if (folder / "data").is_dir() and (folder / "src").is_dir():
            return folder

    raise FileNotFoundError(
        "Could not find a project folder containing data and src."
    )


def load_contract(path: Path) -> dict:
    """Read the YAML experiment contract."""

    with Path(path).open("r", encoding="utf-8") as stream:
        contract = yaml.safe_load(stream)

    if not isinstance(contract, dict):
        raise ValueError(
            "The experiment contract must contain a YAML mapping."
        )

    return contract


def load_reference(path: Path) -> pd.DataFrame:
    """Load and validate the cleaned Week 2 trajectory reference."""

    reference = pd.read_csv(
        path,
        parse_dates=["Timestamp"],
    )

    missing = sorted(
        set(REQUIRED_REFERENCE_COLUMNS) - set(reference.columns)
    )

    if missing:
        raise ValueError(
            f"Cleaned reference is missing columns: {missing}"
        )

    if reference[REQUIRED_REFERENCE_COLUMNS].isna().any().any():
        counts = reference[
            REQUIRED_REFERENCE_COLUMNS
        ].isna().sum()

        raise ValueError(
            "Missing required reference values:\n"
            + counts.to_string()
        )

    reference = reference.sort_values(
        ["AnimalID", "SegmentID", "Timestamp"],
        kind="mergesort",
    ).reset_index(drop=True)

    if reference.duplicated(
        ["AnimalID", "Timestamp"]
    ).any():
        raise ValueError(
            "Duplicate AnimalID-Timestamp events remain."
        )

    segment_animals = (
        reference.groupby("SegmentID")["AnimalID"].nunique()
    )

    if not segment_animals.eq(1).all():
        raise ValueError(
            "A SegmentID is associated with multiple animals."
        )

    non_increasing = (
        reference.groupby("SegmentID")["Timestamp"]
        .diff()
        .dt.total_seconds()
        .le(0)
    )

    if non_increasing.any():
        raise ValueError(
            "Timestamps are not strictly increasing inside every segment."
        )

    return reference


def interval_to_stride(interval_minutes: int) -> int:
    """Convert a supported nominal interval to a row stride."""

    if interval_minutes not in SUPPORTED_INTERVALS:
        raise ValueError(
            f"Unsupported interval {interval_minutes}. "
            f"Choose one of {SUPPORTED_INTERVALS}."
        )

    return interval_minutes // BASE_INTERVAL_MINUTES


def make_downsampling_mask(
    segment: pd.DataFrame,
    interval_minutes: int,
    offset: int,
) -> pd.DataFrame:
    """Identify retained and eligible withheld GPS fixes.

    A withheld fix is eligible only when it lies strictly between
    retained anchors. Points outside that range would require
    extrapolation and are therefore excluded.

    The segment is sorted only when necessary, and the output DataFrame
    is constructed in one operation to reduce repeated pandas work.
    """

    if segment.empty:
        raise ValueError("The segment is empty.")

    if segment["SegmentID"].nunique() != 1:
        raise ValueError(
            "Pass exactly one SegmentID."
        )

    if not segment[
        "Timestamp"
    ].is_monotonic_increasing:
        segment = segment.sort_values(
            "Timestamp",
            kind="mergesort",
        )

    segment = segment.reset_index(
        drop=True
    )

    stride = interval_to_stride(
        interval_minutes
    )

    if offset not in range(stride):
        raise ValueError(
            f"Offset must be between 0 and {stride - 1}."
        )

    positions = np.arange(
        len(segment),
        dtype=np.int64,
    )

    retained = (
        positions % stride == offset
    )

    retained_positions = positions[
        retained
    ]

    if len(retained_positions) == 0:
        eligible = np.zeros(
            len(segment),
            dtype=bool,
        )

        reasons = np.full(
            len(segment),
            "no_retained_anchor",
            dtype=object,
        )

    else:
        first_anchor = int(
            retained_positions[0]
        )

        last_anchor = int(
            retained_positions[-1]
        )

        eligible = (
            (~retained)
            & (positions > first_anchor)
            & (positions < last_anchor)
        )

        reasons = np.select(
            [
                retained,
                positions < first_anchor,
                positions > last_anchor,
                eligible,
            ],
            [
                "retained_anchor",
                "before_first_anchor",
                "after_last_anchor",
                "eligible_withheld",
            ],
            default="not_eligible",
        )

    result = pd.DataFrame(
        {
            "SourceRowNumber": segment[
                "SourceRowNumber"
            ].array,
            "AnimalID": segment[
                "AnimalID"
            ].array,
            "SegmentID": segment[
                "SegmentID"
            ].array,
            "Timestamp": segment[
                "Timestamp"
            ].array,
            "Interval_min": np.full(
                len(segment),
                interval_minutes,
                dtype=np.int64,
            ),
            "Offset": np.full(
                len(segment),
                offset,
                dtype=np.int64,
            ),
            "PositionInSegment": positions,
            "Retained": retained,
            "EligibleWithheld": eligible,
            "MaskReason": reasons,
        }
    )

    return result




def interpolate_xy(
    anchor_time_s: Iterable[float],
    anchor_x_m: Iterable[float],
    anchor_y_m: Iterable[float],
    query_time_s: Iterable[float],
    method: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate local metre coordinates.

    Raises
    ------
    ValueError
        If the method is unsupported, anchors are insufficient,
        anchor times are unordered, or extrapolation is requested.
    """

    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"Unsupported method: {method}"
        )

    t = np.asarray(
        anchor_time_s,
        dtype=np.float64,
    )

    x = np.asarray(
        anchor_x_m,
        dtype=np.float64,
    )

    y = np.asarray(
        anchor_y_m,
        dtype=np.float64,
    )

    q = np.asarray(
        query_time_s,
        dtype=np.float64,
    )

    if not (len(t) == len(x) == len(y)):
        raise ValueError(
            "Anchor time, x and y arrays must have equal lengths."
        )

    if len(t) < MINIMUM_ANCHORS[method]:
        raise ValueError(
            f"{method} requires at least "
            f"{MINIMUM_ANCHORS[method]} retained anchors."
        )

    if np.any(np.diff(t) <= 0):
        raise ValueError(
            "Anchor times must be strictly increasing."
        )

    if q.size and (
        q.min() < t[0]
        or q.max() > t[-1]
    ):
        raise ValueError(
            "A query is outside the retained anchor range; "
            "no extrapolation."
        )

    if method == "linear":
        estimated_x = np.interp(q, t, x)
        estimated_y = np.interp(q, t, y)

        return estimated_x, estimated_y

    if method == "cubic":
        x_model = CubicSpline(
            t,
            x,
            bc_type="natural",
            extrapolate=False,
        )

        y_model = CubicSpline(
            t,
            y,
            bc_type="natural",
            extrapolate=False,
        )

    else:
        x_model = PchipInterpolator(
            t,
            x,
            extrapolate=False,
        )

        y_model = PchipInterpolator(
            t,
            y,
            extrapolate=False,
        )

    return (
        np.asarray(x_model(q)),
        np.asarray(y_model(q)),
    )


def local_xy_to_latlon(
    x_m: Iterable[float],
    y_m: Iterable[float],
    origin_latitude: float,
    origin_longitude: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Invert the Week 2 local-coordinate calculation."""

    x = np.asarray(
        x_m,
        dtype=np.float64,
    )

    y = np.asarray(
        y_m,
        dtype=np.float64,
    )

    latitude = (
        origin_latitude
        + np.degrees(y / EARTH_RADIUS_M)
    )

    longitude = (
        origin_longitude
        + np.degrees(
            x
            / (
                EARTH_RADIUS_M
                * np.cos(
                    np.radians(origin_latitude)
                )
            )
        )
    )

    return latitude, longitude


def haversine_m(
    latitude_1: Iterable[float] | float,
    longitude_1: Iterable[float] | float,
    latitude_2: Iterable[float] | float,
    longitude_2: Iterable[float] | float,
) -> np.ndarray:
    """Return great-circle distances in metres."""

    lat1 = np.radians(
        np.asarray(latitude_1, dtype=np.float64)
    )

    lon1 = np.radians(
        np.asarray(longitude_1, dtype=np.float64)
    )

    lat2 = np.radians(
        np.asarray(latitude_2, dtype=np.float64)
    )

    lon2 = np.radians(
        np.asarray(longitude_2, dtype=np.float64)
    )

    delta_latitude = lat2 - lat1
    delta_longitude = lon2 - lon1

    a = (
        np.sin(delta_latitude / 2.0) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(delta_longitude / 2.0) ** 2
    )

    a = np.clip(
        a,
        0.0,
        1.0,
    )

    return (
        2.0
        * EARTH_RADIUS_M
        * np.arctan2(
            np.sqrt(a),
            np.sqrt(1.0 - a),
        )
    )


def _origin_for_animal(
    reference: pd.DataFrame,
    animal_id: str,
) -> tuple[float, float]:
    """Return the Week 2 local-coordinate origin."""

    animal = reference.loc[
        reference["AnimalID"].eq(
            animal_id
        )
    ]

    if animal.empty:
        raise ValueError(
            f"Animal not found: {animal_id}"
        )

    if not animal[
        "Timestamp"
    ].is_monotonic_increasing:
        animal = animal.sort_values(
            "Timestamp",
            kind="mergesort",
        )

    first = animal.iloc[0]

    return (
        float(first["Latitude"]),
        float(first["Longitude"]),
    )


def _path_length_m(
    latitude: np.ndarray,
    longitude: np.ndarray,
) -> float:
    """Calculate consecutive Haversine path length."""

    if len(latitude) < 2:
        return 0.0

    steps = haversine_m(
        latitude[:-1],
        longitude[:-1],
        latitude[1:],
        longitude[1:],
    )

    return float(steps.sum())


def reconstruct_case(
    reference: pd.DataFrame,
    segment_id: str,
    interval_minutes: int,
    offset: int,
    method: str,
) -> tuple[pd.DataFrame, dict]:
    """Reconstruct and score one experiment case."""

    segment = reference.loc[
        reference["SegmentID"].eq(segment_id)
    ].copy()

    if segment.empty:
        raise ValueError(
            f"Segment not found: {segment_id}"
        )

    if not segment[
        "Timestamp"
    ].is_monotonic_increasing:
        segment = segment.sort_values(
            "Timestamp",
            kind="mergesort",
        )

    segment = segment.reset_index(
        drop=True
    )

    mask = make_downsampling_mask(
        segment,
        interval_minutes,
        offset,
    )

    anchors = segment.loc[
        mask["Retained"].to_numpy()
    ].copy()

    withheld = segment.loc[
        mask["EligibleWithheld"].to_numpy()
    ].copy()

    base_case = {
        "AnimalID": str(
            segment["AnimalID"].iloc[0]
        ),
        "SegmentID": segment_id,
        "Method": method,
        "Interval_min": interval_minutes,
        "Offset": offset,
        "SegmentFixes": int(len(segment)),
        "RetainedAnchors": int(len(anchors)),
        "EligibleWithheld": int(len(withheld)),
    }

    if len(anchors) < MINIMUM_ANCHORS[method]:
        return pd.DataFrame(), {
            **base_case,
            "Status": "insufficient_anchors",
            "Runtime_s": 0.0,
        }

    if withheld.empty:
        return pd.DataFrame(), {
            **base_case,
            "Status": "no_eligible_withheld_fixes",
            "Runtime_s": 0.0,
        }

    segment_start = segment[
        "Timestamp"
    ].iloc[0]

    anchor_time_s = (
        anchors["Timestamp"] - segment_start
    ).dt.total_seconds().to_numpy()

    query_time_s = (
        withheld["Timestamp"] - segment_start
    ).dt.total_seconds().to_numpy()

    started = perf_counter()

    estimated_x, estimated_y = interpolate_xy(
        anchor_time_s,
        anchors["LocalX_m"].to_numpy(),
        anchors["LocalY_m"].to_numpy(),
        query_time_s,
        method,
    )

    runtime_s = perf_counter() - started

    origin_latitude, origin_longitude = (
        _origin_for_animal(
            reference,
            base_case["AnimalID"],
        )
    )

    estimated_latitude, estimated_longitude = (
        local_xy_to_latlon(
            estimated_x,
            estimated_y,
            origin_latitude,
            origin_longitude,
        )
    )

    position_error = haversine_m(
        withheld["Latitude"].to_numpy(),
        withheld["Longitude"].to_numpy(),
        estimated_latitude,
        estimated_longitude,
    )

    right_anchor_index = np.searchsorted(
        anchor_time_s,
        query_time_s,
        side="right",
    )

    left_anchor_index = (
        right_anchor_index - 1
    )

    anchor_x = anchors[
        "LocalX_m"
    ].to_numpy()

    anchor_y = anchors[
        "LocalY_m"
    ].to_numpy()

    left_x = anchor_x[
        left_anchor_index
    ]

    right_x = anchor_x[
        right_anchor_index
    ]

    left_y = anchor_y[
        left_anchor_index
    ]

    right_y = anchor_y[
        right_anchor_index
    ]

    tolerance = 1e-9

    overshoot = (
        (
            estimated_x
            < np.minimum(left_x, right_x)
            - tolerance
        )
        | (
            estimated_x
            > np.maximum(left_x, right_x)
            + tolerance
        )
        | (
            estimated_y
            < np.minimum(left_y, right_y)
            - tolerance
        )
        | (
            estimated_y
            > np.maximum(left_y, right_y)
            + tolerance
        )
    )

    prediction_columns = [
        "SourceRowNumber",
        "AnimalID",
        "SegmentID",
        "Timestamp",
        "Latitude",
        "Longitude",
        "LocalX_m",
        "LocalY_m",
    ]

    prediction_details = pd.DataFrame(
        {
            "Method": np.full(
                len(withheld),
                method,
                dtype=object,
            ),
            "Interval_min": np.full(
                len(withheld),
                interval_minutes,
                dtype=np.int64,
            ),
            "Offset": np.full(
                len(withheld),
                offset,
                dtype=np.int64,
            ),
            "EstimatedX_m": estimated_x,
            "EstimatedY_m": estimated_y,
            "EstimatedLatitude": (
                estimated_latitude
            ),
            "EstimatedLongitude": (
                estimated_longitude
            ),
            "PositionError_m": (
                position_error
            ),
            "CoordinateOvershoot": (
                overshoot
            ),
        },
        index=withheld.index,
    )

    predictions = pd.concat(
        [
            withheld[
                prediction_columns
            ].copy(),
            prediction_details,
        ],
        axis=1,
    )

    first_anchor_time = anchors[
        "Timestamp"
    ].iloc[0]

    last_anchor_time = anchors[
        "Timestamp"
    ].iloc[-1]

    supported = segment["Timestamp"].between(
        first_anchor_time,
        last_anchor_time,
    )

    full_path = (
        segment.loc[supported]
        .copy()
        .reset_index(drop=True)
    )

    predicted_lookup = predictions.set_index(
        "SourceRowNumber"
    )

    full_path["ReconstructedX_m"] = (
        full_path["LocalX_m"]
    )

    full_path["ReconstructedY_m"] = (
        full_path["LocalY_m"]
    )

    withheld_ids = full_path[
        "SourceRowNumber"
    ].isin(predicted_lookup.index)

    source_ids = full_path.loc[
        withheld_ids,
        "SourceRowNumber",
    ]

    full_path.loc[
        withheld_ids,
        "ReconstructedX_m",
    ] = source_ids.map(
        predicted_lookup["EstimatedX_m"]
    ).to_numpy()

    full_path.loc[
        withheld_ids,
        "ReconstructedY_m",
    ] = source_ids.map(
        predicted_lookup["EstimatedY_m"]
    ).to_numpy()

    reconstructed_latitude, reconstructed_longitude = (
        local_xy_to_latlon(
            full_path[
                "ReconstructedX_m"
            ].to_numpy(),
            full_path[
                "ReconstructedY_m"
            ].to_numpy(),
            origin_latitude,
            origin_longitude,
        )
    )

    reference_path_m = _path_length_m(
        full_path["Latitude"].to_numpy(),
        full_path["Longitude"].to_numpy(),
    )

    reconstructed_path_m = _path_length_m(
        reconstructed_latitude,
        reconstructed_longitude,
    )

    if reference_path_m > 0:
        signed_path_error_percent = (
            100.0
            * (
                reconstructed_path_m
                - reference_path_m
            )
            / reference_path_m
        )

    else:
        signed_path_error_percent = np.nan

    step_seconds = (
        full_path["Timestamp"]
        .diff()
        .dt.total_seconds()
        .to_numpy()[1:]
    )

    reconstructed_steps = haversine_m(
        reconstructed_latitude[:-1],
        reconstructed_longitude[:-1],
        reconstructed_latitude[1:],
        reconstructed_longitude[1:],
    )

    if len(reconstructed_steps):
        maximum_speed = float(
            np.max(
                reconstructed_steps
                / step_seconds
            )
        )

    else:
        maximum_speed = np.nan

    case = {
        **base_case,
        "Status": "ok",
        "Runtime_s": runtime_s,
        "MedianError_m": float(
            np.median(position_error)
        ),
        "MAE_m": float(
            np.mean(np.abs(position_error))
        ),
        "RMSE_m": float(
            np.sqrt(
                np.mean(position_error**2)
            )
        ),
        "P95Error_m": float(
            np.quantile(
                position_error,
                0.95,
            )
        ),
        "MaxError_m": float(
            np.max(position_error)
        ),
        "CoordinateOvershootCount": int(
            np.sum(overshoot)
        ),
        "ReferencePathLength_m": (
            reference_path_m
        ),
        "ReconstructedPathLength_m": (
            reconstructed_path_m
        ),
        "SignedPathLengthError_percent": (
            signed_path_error_percent
        ),
        "AbsolutePathLengthError_percent": abs(
            signed_path_error_percent
        ),
        "MaximumReconstructedSpeed_mps": (
            maximum_speed
        ),
    }

    return predictions, case


def run_pilot(
    reference: pd.DataFrame,
    segment_ids: Sequence[str],
    intervals: Sequence[int],
    methods: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all offsets on a development subset."""

    prediction_frames = []
    cases = []

    for segment_id in segment_ids:
        for interval in intervals:
            stride = interval_to_stride(
                interval
            )

            for offset in range(stride):
                for method in methods:
                    predictions, case = (
                        reconstruct_case(
                            reference,
                            segment_id,
                            interval,
                            offset,
                            method,
                        )
                    )

                    cases.append(case)

                    if not predictions.empty:
                        prediction_frames.append(
                            predictions
                        )

    if prediction_frames:
        all_predictions = pd.concat(
            prediction_frames,
            ignore_index=True,
        )

    else:
        all_predictions = pd.DataFrame()

    return (
        all_predictions,
        pd.DataFrame(cases),
    )


def summarise_pilot(
    predictions: pd.DataFrame,
    cases: pd.DataFrame,
) -> pd.DataFrame:
    """Create the pilot method comparison table."""

    good_cases = cases.loc[
        cases["Status"].eq("ok")
    ].copy()

    position_summary = (
        predictions.groupby(
            ["Method", "Interval_min"],
            sort=True,
        )
        .agg(
            PredictedFixes=(
                "PositionError_m",
                "size",
            ),
            MedianPositionError_m=(
                "PositionError_m",
                "median",
            ),
            MAE_m=(
                "PositionError_m",
                "mean",
            ),
            RMSE_m=(
                "PositionError_m",
                lambda values: float(
                    np.sqrt(
                        np.mean(
                            np.square(values)
                        )
                    )
                ),
            ),
            P95PositionError_m=(
                "PositionError_m",
                lambda values: values.quantile(
                    0.95
                ),
            ),
            MaximumPositionError_m=(
                "PositionError_m",
                "max",
            ),
            OvershootCount=(
                "CoordinateOvershoot",
                "sum",
            ),
        )
        .reset_index()
    )

    position_summary[
        "OvershootPercent"
    ] = (
        100.0
        * position_summary["OvershootCount"]
        / position_summary["PredictedFixes"]
    )

    case_summary = (
        good_cases.groupby(
            ["Method", "Interval_min"],
            sort=True,
        )
        .agg(
            SuccessfulCases=(
                "Status",
                "size",
            ),
            MedianAbsolutePathError_percent=(
                "AbsolutePathLengthError_percent",
                "median",
            ),
            P95AbsolutePathError_percent=(
                "AbsolutePathLengthError_percent",
                lambda values: values.quantile(
                    0.95
                ),
            ),
            MaximumReconstructedSpeed_mps=(
                "MaximumReconstructedSpeed_mps",
                "max",
            ),
            TotalInterpolationRuntime_s=(
                "Runtime_s",
                "sum",
            ),
        )
        .reset_index()
    )

    failure_summary = (
        cases.assign(
            Failed=~cases["Status"].eq("ok")
        )
        .groupby(
            ["Method", "Interval_min"],
            sort=True,
        )
        .agg(
            TotalCases=("Status", "size"),
            FailedCases=("Failed", "sum"),
        )
        .reset_index()
    )

    return (
        position_summary
        .merge(
            case_summary,
            on=["Method", "Interval_min"],
        )
        .merge(
            failure_summary,
            on=["Method", "Interval_min"],
        )
    )


def build_support_audit(
    reference: pd.DataFrame,
    intervals: Sequence[int],
    methods: Sequence[str],
) -> pd.DataFrame:
    """Count supported cases without reconstructing them."""

    rows = []

    for segment_id, segment in reference.groupby(
        "SegmentID",
        sort=True,
    ):
        animal_id = str(
            segment["AnimalID"].iloc[0]
        )

        for interval in intervals:
            stride = interval_to_stride(
                interval
            )

            for offset in range(stride):
                mask = make_downsampling_mask(
                    segment,
                    interval,
                    offset,
                )

                anchors = int(
                    mask["Retained"].sum()
                )

                eligible = int(
                    mask[
                        "EligibleWithheld"
                    ].sum()
                )

                for method in methods:
                    if (
                        anchors
                        < MINIMUM_ANCHORS[method]
                    ):
                        status = (
                            "insufficient_anchors"
                        )
                        usable = 0

                    elif eligible == 0:
                        status = (
                            "no_eligible_withheld_fixes"
                        )
                        usable = 0

                    else:
                        status = "supported"
                        usable = eligible

                    rows.append(
                        {
                            "AnimalID": animal_id,
                            "SegmentID": segment_id,
                            "Interval_min": interval,
                            "Offset": offset,
                            "Method": method,
                            "SegmentFixes": int(
                                len(segment)
                            ),
                            "RetainedAnchors": anchors,
                            "EligibleWithheld": eligible,
                            "UsableWithheld": usable,
                            "Status": status,
                        }
                    )

    return pd.DataFrame(rows)


def summarise_support(
    support: pd.DataFrame,
) -> pd.DataFrame:
    """Summarise coverage and common supported cases."""

    method_summary = (
        support.assign(
            Supported=support[
                "Status"
            ].eq("supported")
        )
        .groupby(
            ["Method", "Interval_min"],
            sort=True,
        )
        .agg(
            Cases=("Status", "size"),
            SupportedCases=(
                "Supported",
                "sum",
            ),
            UsableWithheld=(
                "UsableWithheld",
                "sum",
            ),
        )
        .reset_index()
    )

    method_count = support[
        "Method"
    ].nunique()

    case_keys = [
        "AnimalID",
        "SegmentID",
        "Interval_min",
        "Offset",
    ]

    common = (
        support.assign(
            Supported=support[
                "Status"
            ].eq("supported")
        )
        .groupby(
            case_keys,
            sort=True,
        )
        .agg(
            SupportingMethods=(
                "Supported",
                "sum",
            ),
            EligibleWithheld=(
                "EligibleWithheld",
                "first",
            ),
        )
        .reset_index()
    )

    common[
        "CommonSupportedCase"
    ] = common[
        "SupportingMethods"
    ].eq(method_count)

    common_summary_rows = []

    for interval, interval_data in common.groupby(
        "Interval_min",
        sort=True,
    ):
        common_cases = interval_data[
            "CommonSupportedCase"
        ]

        common_summary_rows.append(
            {
                "Interval_min": interval,
                "CommonSupportedCases": int(
                    common_cases.sum()
                ),
                "CommonEligibleWithheld": int(
                    interval_data.loc[
                        common_cases,
                        "EligibleWithheld",
                    ].sum()
                ),
            }
        )

    common_summary = pd.DataFrame(
        common_summary_rows
    )

    return method_summary.merge(
        common_summary,
        on="Interval_min",
        how="left",
    )