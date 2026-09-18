"""Clean, segment, describe and export the reduced elephant GPS trajectories.

Week 2 of the MMA3001 project. The raw Excel workbook is read but never edited.
Exact-coordinate CSV outputs and candidate-spike plots must remain outside the
public GitHub repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


EARTH_RADIUS_M = 6_371_000.0
GAP_THRESHOLD_MINUTES = 30.0
SPIKE_SPEED_THRESHOLD_MPS = 5.0
EXPECTED_RAW_ROWS = 60_000
EXPECTED_ANIMALS = 6
EXPECTED_REMOVED_SPIKES = 6
EXPECTED_CLEAN_ROWS = 59_994
EXPECTED_RAW_LONG_GAPS = 70
EXPECTED_CLEAN_LONG_GAPS = 71
EXPECTED_SEGMENTS = 77

REQUIRED_COLUMNS = ["AnimalID", "Timestamp", "Latitude", "Longitude"]
NUMERIC_COLUMNS = [
    "Year",
    "DayOfYear",
    "Latitude",
    "Longitude",
    "HDOP",
    "RecordsCombined",
]

# These six events are removed only after the student completes decision D1.
# They are the six points flagged by the Week 1 rule:
# incoming speed > 5 m/s AND outgoing speed > 5 m/s.
APPROVED_SPIKE_EVENTS = {
    ("LOAF-18-f-2981-1", pd.Timestamp("2019-06-13 09:00:00")),
    ("LOAF-18-f-2981-1", pd.Timestamp("2019-06-13 11:00:00")),
    ("LOAF-18-f-2981-1", pd.Timestamp("2019-06-13 11:15:00")),
    ("LOAF-18-f-2981-1", pd.Timestamp("2019-08-29 23:30:00")),
    ("LOAF-18-f-2982-1", pd.Timestamp("2019-07-19 17:45:00")),
    ("LOAF-18-f-2986-1", pd.Timestamp("2019-07-30 14:00:00")),
}


def find_project_root(start: Path | None = None) -> Path:
    """Return the project folder containing data/raw and src."""

    candidates: list[Path] = []
    if start is not None:
        candidates.append(Path(start).resolve())
    candidates.extend([Path.cwd().resolve(), Path(__file__).resolve().parents[1]])

    checked: set[Path] = set()
    for candidate in candidates:
        for folder in [candidate, *candidate.parents]:
            if folder in checked:
                continue
            checked.add(folder)
            if (folder / "data" / "raw").exists() and (folder / "src").exists():
                return folder

    raise FileNotFoundError(
        "Could not find the project folder containing data/raw and src."
    )


def find_workbook(raw_folder: Path) -> Path:
    """Find the single reduced elephant workbook in data/raw."""

    patterns = [
        "Elephant_GPS_Reduced_60000*.xlsx",
        "elephant_gps_reduced_60000*.xlsx",
    ]
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(raw_folder.glob(pattern))
    matches = sorted(set(matches))

    if len(matches) != 1:
        raise FileNotFoundError(
            "Expected exactly one Elephant_GPS_Reduced_60000 Excel workbook "
            f"in {raw_folder}, but found {len(matches)}."
        )
    return matches[0]


def haversine_m(
    latitude_1: Iterable[float] | float,
    longitude_1: Iterable[float] | float,
    latitude_2: Iterable[float] | float,
    longitude_2: Iterable[float] | float,
) -> np.ndarray:
    """Calculate great-circle distance in metres between WGS84 coordinates."""

    lat1 = np.radians(np.asarray(latitude_1, dtype=float))
    lon1 = np.radians(np.asarray(longitude_1, dtype=float))
    lat2 = np.radians(np.asarray(latitude_2, dtype=float))
    lon2 = np.radians(np.asarray(longitude_2, dtype=float))

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2.0) ** 2
    )
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_M * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))


def load_and_standardise(workbook_path: Path) -> tuple[pd.DataFrame, dict]:
    """Read GPS_Data, validate essential fields and standardise types."""

    raw = pd.read_excel(workbook_path, sheet_name="GPS_Data")
    raw.columns = raw.columns.astype(str).str.strip()

    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(raw.columns))
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df = raw.copy()
    df.insert(0, "SourceRowNumber", np.arange(2, len(df) + 2, dtype=int))
    df["AnimalID"] = df["AnimalID"].astype("string").str.strip()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    required_missing = df[REQUIRED_COLUMNS].isna().sum()
    if int(required_missing.sum()) != 0:
        raise ValueError(
            "Required values are missing after parsing:\n"
            + required_missing.to_string()
        )

    invalid_latitude = ~df["Latitude"].between(-90.0, 90.0, inclusive="both")
    invalid_longitude = ~df["Longitude"].between(-180.0, 180.0, inclusive="both")
    if invalid_latitude.any() or invalid_longitude.any():
        raise ValueError(
            "Coordinates outside WGS84 ranges were found: "
            f"latitude={int(invalid_latitude.sum())}, "
            f"longitude={int(invalid_longitude.sum())}."
        )

    source_year_mismatches = 0
    source_day_mismatches = 0
    if "Year" in df.columns:
        source_year_mismatches = int(
            (df["Year"].notna() & (df["Year"] != df["Timestamp"].dt.year)).sum()
        )
    if "DayOfYear" in df.columns:
        source_day_mismatches = int(
            (
                df["DayOfYear"].notna()
                & (df["DayOfYear"] != df["Timestamp"].dt.dayofyear)
            ).sum()
        )

    duplicate_mask = df.duplicated(["AnimalID", "Timestamp"], keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    duplicate_events = int(
        df.loc[duplicate_mask, ["AnimalID", "Timestamp"]].drop_duplicates().shape[0]
    )

    if duplicate_events:
        aggregation: dict[str, str] = {
            "SourceRowNumber": lambda values: ",".join(map(str, values)),
            "Latitude": "median",
            "Longitude": "median",
        }
        for optional in ["Species", "HDOP", "RecordsCombined"]:
            if optional in df.columns:
                aggregation[optional] = "first" if optional == "Species" else "median"
        df = (
            df.groupby(["AnimalID", "Timestamp"], as_index=False, sort=False)
            .agg(aggregation)
        )

    df["Year"] = df["Timestamp"].dt.year.astype(int)
    df["DayOfYear"] = df["Timestamp"].dt.dayofyear.astype(int)
    df = df.sort_values(["AnimalID", "Timestamp"], kind="mergesort").reset_index(
        drop=True
    )

    time_differences = df.groupby("AnimalID")["Timestamp"].diff()
    raw_gap_minutes = time_differences.dt.total_seconds() / 60.0

    audit = {
        "source_rows": int(len(raw)),
        "standardised_rows": int(len(df)),
        "animal_count": int(df["AnimalID"].nunique()),
        "required_missing_values": int(required_missing.sum()),
        "invalid_latitudes": int(invalid_latitude.sum()),
        "invalid_longitudes": int(invalid_longitude.sum()),
        "source_year_mismatches": source_year_mismatches,
        "source_day_of_year_mismatches": source_day_mismatches,
        "duplicate_rows": duplicate_rows,
        "duplicate_events_consolidated": duplicate_events,
        "raw_gaps_above_30_minutes": int(
            (raw_gap_minutes > GAP_THRESHOLD_MINUTES).sum()
        ),
        "modal_interval_minutes": float(raw_gap_minutes.mode().iloc[0]),
        "median_interval_minutes": float(raw_gap_minutes.median()),
    }
    return df, audit


def screen_spike_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Flag points whose incoming and outgoing adjacent speeds both exceed 5 m/s."""

    screened = df.copy()
    grouped = screened.groupby("AnimalID", sort=False)

    previous_time = grouped["Timestamp"].shift(1)
    next_time = grouped["Timestamp"].shift(-1)
    previous_latitude = grouped["Latitude"].shift(1)
    previous_longitude = grouped["Longitude"].shift(1)
    next_latitude = grouped["Latitude"].shift(-1)
    next_longitude = grouped["Longitude"].shift(-1)

    seconds_from_previous = (screened["Timestamp"] - previous_time).dt.total_seconds()
    seconds_to_next = (next_time - screened["Timestamp"]).dt.total_seconds()

    distance_from_previous = haversine_m(
        previous_latitude,
        previous_longitude,
        screened["Latitude"],
        screened["Longitude"],
    )
    distance_to_next = haversine_m(
        screened["Latitude"],
        screened["Longitude"],
        next_latitude,
        next_longitude,
    )
    neighbour_bridge_distance = haversine_m(
        previous_latitude,
        previous_longitude,
        next_latitude,
        next_longitude,
    )

    screened["IncomingInterval_min"] = seconds_from_previous / 60.0
    screened["OutgoingInterval_min"] = seconds_to_next / 60.0
    screened["IncomingDistance_m"] = distance_from_previous
    screened["OutgoingDistance_m"] = distance_to_next
    screened["NeighbourBridgeDistance_m"] = neighbour_bridge_distance
    screened["IncomingSpeed_mps"] = distance_from_previous / seconds_from_previous
    screened["OutgoingSpeed_mps"] = distance_to_next / seconds_to_next

    candidate_mask = (
        screened["IncomingSpeed_mps"].gt(SPIKE_SPEED_THRESHOLD_MPS)
        & screened["OutgoingSpeed_mps"].gt(SPIKE_SPEED_THRESHOLD_MPS)
    )
    candidates = screened.loc[candidate_mask].copy()
    candidates["ScreenRule"] = (
        "IncomingSpeed_mps > 5.0 AND OutgoingSpeed_mps > 5.0"
    )
    return candidates.reset_index(drop=True)


def plot_candidate_spikes(
    df: pd.DataFrame,
    candidates: pd.DataFrame,
    output_path: Path,
    points_each_side: int = 3,
) -> None:
    """Save a private relative-coordinate plot for visual D1 inspection."""

    fig, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    axes = axes.ravel()

    for axis, candidate in zip(axes, candidates.itertuples(index=False), strict=True):
        animal_data = df[df["AnimalID"] == candidate.AnimalID].reset_index(drop=True)
        candidate_position = animal_data.index[
            animal_data["Timestamp"] == candidate.Timestamp
        ]
        if len(candidate_position) != 1:
            raise ValueError("Candidate timestamp was not unique within its animal.")
        centre = int(candidate_position[0])
        start = max(0, centre - points_each_side)
        stop = min(len(animal_data), centre + points_each_side + 1)
        window = animal_data.iloc[start:stop].copy()

        centre_row = animal_data.iloc[centre]
        latitude_0 = float(centre_row["Latitude"])
        longitude_0 = float(centre_row["Longitude"])
        window["RelativeX_m"] = (
            EARTH_RADIUS_M
            * np.radians(window["Longitude"] - longitude_0)
            * np.cos(np.radians(latitude_0))
        )
        window["RelativeY_m"] = EARTH_RADIUS_M * np.radians(
            window["Latitude"] - latitude_0
        )

        axis.plot(
            window["RelativeX_m"],
            window["RelativeY_m"],
            color="#4C78A8",
            marker="o",
            linewidth=1.5,
        )
        candidate_row = window[window["Timestamp"] == candidate.Timestamp]
        axis.scatter(
            candidate_row["RelativeX_m"],
            candidate_row["RelativeY_m"],
            color="#D62728",
            marker="X",
            s=100,
            zorder=5,
            label="Screened point",
        )
        axis.set_title(
            f"{candidate.AnimalID}\n{candidate.Timestamp:%Y-%m-%d %H:%M}"
        )
        axis.set_xlabel("Relative east-west position (m)")
        axis.set_ylabel("Relative north-south position (m)")
        axis.set_aspect("equal", adjustable="datalim")
        axis.legend(loc="best", fontsize=8)

    fig.suptitle("D1 inspection: six adjacent-speed spike candidates", fontsize=14)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def remove_approved_spikes(
    df: pd.DataFrame, candidates: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove only the six event keys explicitly approved at decision D1."""

    candidate_keys = set(
        zip(candidates["AnimalID"], candidates["Timestamp"], strict=True)
    )
    if candidate_keys != APPROVED_SPIKE_EVENTS:
        missing = sorted(APPROVED_SPIKE_EVENTS - candidate_keys)
        unexpected = sorted(candidate_keys - APPROVED_SPIKE_EVENTS)
        raise ValueError(
            "The speed screen does not match the six approved D1 events. "
            f"Missing={missing}; unexpected={unexpected}. Do not delete anything."
        )

    row_keys = pd.MultiIndex.from_frame(df[["AnimalID", "Timestamp"]])
    approved_index = pd.MultiIndex.from_tuples(
        sorted(APPROVED_SPIKE_EVENTS), names=["AnimalID", "Timestamp"]
    )
    removal_mask = row_keys.isin(approved_index)

    removed = df.loc[removal_mask].copy()
    diagnostic_columns = [
        "AnimalID",
        "Timestamp",
        "IncomingInterval_min",
        "OutgoingInterval_min",
        "IncomingDistance_m",
        "OutgoingDistance_m",
        "NeighbourBridgeDistance_m",
        "IncomingSpeed_mps",
        "OutgoingSpeed_mps",
        "ScreenRule",
    ]
    removed = removed.merge(
        candidates[diagnostic_columns],
        on=["AnimalID", "Timestamp"],
        how="left",
        validate="one_to_one",
    )
    removed["RemovalReason"] = (
        "Approved at D1: both adjacent speeds exceeded 5 m/s and the local "
        "trajectory inspection supported a GPS spatial spike."
    )

    cleaned = df.loc[~removal_mask].copy()
    cleaned = cleaned.sort_values(["AnimalID", "Timestamp"], kind="mergesort")
    cleaned = cleaned.reset_index(drop=True)

    if len(removed) != EXPECTED_REMOVED_SPIKES:
        raise AssertionError(
            f"Expected {EXPECTED_REMOVED_SPIKES} removals, found {len(removed)}."
        )
    return cleaned, removed


def segment_trajectories(df: pd.DataFrame) -> pd.DataFrame:
    """Start a new segment after every within-animal gap greater than 30 minutes."""

    segmented = df.copy()
    grouped = segmented.groupby("AnimalID", sort=False)
    segmented["GapFromPrevious_min"] = (
        grouped["Timestamp"].diff().dt.total_seconds() / 60.0
    )
    segmented["SegmentStart"] = (
        segmented["GapFromPrevious_min"].isna()
        | segmented["GapFromPrevious_min"].gt(GAP_THRESHOLD_MINUTES)
    )
    segmented["SegmentNumber"] = (
        segmented["SegmentStart"].groupby(segmented["AnimalID"]).cumsum().astype(int)
    )
    segmented["SegmentID"] = (
        segmented["AnimalID"]
        + "_S"
        + segmented["SegmentNumber"].astype(str).str.zfill(3)
    )
    return segmented


def add_movement_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Add segment-safe distance, speed, elapsed time and local metre coordinates."""

    result = df.copy()
    by_segment = result.groupby("SegmentID", sort=False)

    previous_time = by_segment["Timestamp"].shift(1)
    previous_latitude = by_segment["Latitude"].shift(1)
    previous_longitude = by_segment["Longitude"].shift(1)

    result["StepTime_s"] = (result["Timestamp"] - previous_time).dt.total_seconds()
    result["StepDistance_m"] = haversine_m(
        previous_latitude,
        previous_longitude,
        result["Latitude"],
        result["Longitude"],
    )
    result.loc[result["StepTime_s"].isna(), "StepDistance_m"] = np.nan
    result["Speed_mps"] = result["StepDistance_m"] / result["StepTime_s"]
    result["ElapsedSegment_min"] = (
        result["Timestamp"] - by_segment["Timestamp"].transform("min")
    ).dt.total_seconds() / 60.0

    animal_origins = result.groupby("AnimalID", sort=False).agg(
        LocalOriginLatitude=("Latitude", "first"),
        LocalOriginLongitude=("Longitude", "first"),
    )
    result = result.join(animal_origins, on="AnimalID")
    result["LocalX_m"] = (
        EARTH_RADIUS_M
        * np.radians(result["Longitude"] - result["LocalOriginLongitude"])
        * np.cos(np.radians(result["LocalOriginLatitude"]))
    )
    result["LocalY_m"] = EARTH_RADIUS_M * np.radians(
        result["Latitude"] - result["LocalOriginLatitude"]
    )

    previous_x = result.groupby("SegmentID", sort=False)["LocalX_m"].shift(1)
    previous_y = result.groupby("SegmentID", sort=False)["LocalY_m"].shift(1)
    result["LocalEuclideanStep_m"] = np.hypot(
        result["LocalX_m"] - previous_x,
        result["LocalY_m"] - previous_y,
    )
    result["ProjectionDifference_m"] = (
        result["LocalEuclideanStep_m"] - result["StepDistance_m"]
    ).abs()
    result["ProjectionDifference_percent"] = np.where(
        result["StepDistance_m"].gt(0),
        100.0 * result["ProjectionDifference_m"] / result["StepDistance_m"],
        np.nan,
    )
    result["Date"] = result["Timestamp"].dt.date
    return result


def make_summary_tables(
    cleaned: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create animal, segment, daily and projection comparison summaries."""

    animal_summary = (
        cleaned.groupby("AnimalID", sort=True)
        .agg(
            CleanedFixes=("Timestamp", "size"),
            Start=("Timestamp", "min"),
            End=("Timestamp", "max"),
            SegmentCount=("SegmentID", "nunique"),
            MedianGap_min=("GapFromPrevious_min", "median"),
            MaxGap_min=("GapFromPrevious_min", "max"),
            MedianSpeed_mps=("Speed_mps", "median"),
            P95Speed_mps=("Speed_mps", lambda values: values.quantile(0.95)),
            TotalObservedDistance_km=(
                "StepDistance_m",
                lambda values: values.sum() / 1000.0,
            ),
        )
        .reset_index()
    )

    segment_summary = (
        cleaned.groupby(["AnimalID", "SegmentID"], sort=True)
        .agg(
            Fixes=("Timestamp", "size"),
            Start=("Timestamp", "min"),
            End=("Timestamp", "max"),
            Duration_hours=("ElapsedSegment_min", lambda values: values.max() / 60.0),
            ObservedDistance_km=(
                "StepDistance_m",
                lambda values: values.sum() / 1000.0,
            ),
        )
        .reset_index()
    )

    daily = (
        cleaned.groupby(["AnimalID", "Date"], sort=True)
        .agg(
            Fixes=("Timestamp", "size"),
            DayStart=("Timestamp", "min"),
            DayEnd=("Timestamp", "max"),
            Segments=("SegmentID", "nunique"),
        )
        .reset_index()
    )
    daily["Coverage_hours"] = (
        daily["DayEnd"] - daily["DayStart"]
    ).dt.total_seconds() / 3600.0

    day_distance_source = cleaned.copy()
    previous_date = day_distance_source.groupby("SegmentID", sort=False)["Date"].shift(1)
    step_inside_same_date = day_distance_source["Date"].eq(previous_date)
    day_distance_source["WithinDayStepDistance_m"] = day_distance_source[
        "StepDistance_m"
    ].where(step_inside_same_date)
    day_distance = (
        day_distance_source.groupby(["AnimalID", "Date"], sort=True)[
            "WithinDayStepDistance_m"
        ]
        .sum(min_count=1)
        .div(1000.0)
        .rename("WithinDayDistance_km")
        .reset_index()
    )
    daily = daily.merge(day_distance, on=["AnimalID", "Date"], how="left")
    daily["CompleteDay"] = (
        daily["Fixes"].ge(95)
        & daily["Coverage_hours"].ge(23.5)
        & daily["Segments"].eq(1)
    )

    projection_summary = pd.DataFrame(
        {
            "Metric": [
                "median_absolute_difference_m",
                "p95_absolute_difference_m",
                "maximum_absolute_difference_m",
                "median_percentage_difference",
                "p95_percentage_difference",
                "maximum_percentage_difference",
            ],
            "Value": [
                cleaned["ProjectionDifference_m"].median(),
                cleaned["ProjectionDifference_m"].quantile(0.95),
                cleaned["ProjectionDifference_m"].max(),
                cleaned["ProjectionDifference_percent"].median(),
                cleaned["ProjectionDifference_percent"].quantile(0.95),
                cleaned["ProjectionDifference_percent"].max(),
            ],
        }
    )
    return animal_summary, segment_summary, daily, projection_summary


def create_eda_figures(
    cleaned: pd.DataFrame,
    daily_summary: pd.DataFrame,
    figures_folder: Path,
) -> list[Path]:
    """Create the five required public Week 2 exploratory figures."""

    figures_folder.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    saved: list[Path] = []

    # Figure 1: relative paths. Exact WGS84 coordinates are not shown.
    figure, axes = plt.subplots(2, 3, figsize=(14, 9), constrained_layout=True)
    for axis, (animal_id, animal_data) in zip(
        axes.ravel(), cleaned.groupby("AnimalID", sort=True), strict=True
    ):
        axis.plot(
            animal_data["LocalX_m"] / 1000.0,
            animal_data["LocalY_m"] / 1000.0,
            linewidth=0.55,
            color="#2A6F97",
        )
        axis.set_title(animal_id)
        axis.set_xlabel("Relative east-west position (km)")
        axis.set_ylabel("Relative north-south position (km)")
        axis.set_aspect("equal", adjustable="datalim")
    figure.suptitle("Relative movement paths by elephant", fontsize=15)
    path = figures_folder / "week2_01_relative_paths.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    saved.append(path)

    # Figure 2: daily recording coverage heatmap.
    coverage = daily_summary.pivot(
        index="AnimalID", columns="Date", values="Fixes"
    ).sort_index()
    figure, axis = plt.subplots(figsize=(15, 4.2), constrained_layout=True)
    sns.heatmap(
        coverage,
        ax=axis,
        cmap="viridis",
        vmin=0,
        vmax=96,
        cbar_kws={"label": "Retained fixes per calendar day"},
    )
    tick_positions = np.arange(0, coverage.shape[1], 14)
    axis.set_xticks(tick_positions + 0.5)
    axis.set_xticklabels(
        [str(coverage.columns[position]) for position in tick_positions],
        rotation=45,
        ha="right",
    )
    axis.set_title("Daily GPS recording coverage")
    axis.set_xlabel("Date")
    axis.set_ylabel("Animal ID")
    path = figures_folder / "week2_02_recording_coverage.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    saved.append(path)

    # Figure 3: time-gap distribution.
    figure, axis = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    bins = np.arange(0.5, 92.5, 1.0)
    axis.hist(
        cleaned["GapFromPrevious_min"].dropna(),
        bins=bins,
        color="#4C78A8",
        edgecolor="white",
        linewidth=0.25,
    )
    axis.axvline(
        GAP_THRESHOLD_MINUTES,
        color="#D62728",
        linestyle="--",
        linewidth=2,
        label="New segment if gap > 30 min",
    )
    axis.set_yscale("log")
    axis.set_xlim(0, 95)
    axis.set_title("Within-animal recording gaps after spike removal")
    axis.set_xlabel("Gap from previous fix (minutes)")
    axis.set_ylabel("Number of gaps (log scale)")
    axis.legend()
    path = figures_folder / "week2_03_time_gap_distribution.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    saved.append(path)

    # Figure 4: segment-safe speed variation among animals.
    figure, axis = plt.subplots(figsize=(11, 5.8), constrained_layout=True)
    speed_data = cleaned.dropna(subset=["Speed_mps"]).copy()
    sns.boxplot(
        data=speed_data,
        x="AnimalID",
        y="Speed_mps",
        showfliers=False,
        color="#72B7B2",
        ax=axis,
    )
    axis.set_title("Segment-safe movement-speed distributions")
    axis.set_xlabel("Animal ID")
    axis.set_ylabel("Estimated speed (m/s)")
    axis.tick_params(axis="x", rotation=25)
    path = figures_folder / "week2_04_speed_distribution.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    saved.append(path)

    # Figure 5: distance on explicitly defined complete days.
    complete_days = daily_summary[daily_summary["CompleteDay"]].copy()
    figure, axis = plt.subplots(figsize=(11, 5.8), constrained_layout=True)
    sns.boxplot(
        data=complete_days,
        x="AnimalID",
        y="WithinDayDistance_km",
        showfliers=False,
        color="#F2CF5B",
        ax=axis,
    )
    sns.stripplot(
        data=complete_days,
        x="AnimalID",
        y="WithinDayDistance_km",
        color="#3D3D3D",
        alpha=0.35,
        size=2.2,
        ax=axis,
    )
    axis.set_title(
        "Observed distance on complete days "
        "(≥95 fixes, ≥23.5 h coverage, one segment)"
    )
    axis.set_xlabel("Animal ID")
    axis.set_ylabel("Within-day observed distance (km)")
    axis.tick_params(axis="x", rotation=25)
    path = figures_folder / "week2_05_complete_day_distance.png"
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    saved.append(path)

    return saved


def validate_final_outputs(cleaned: pd.DataFrame, removed: pd.DataFrame) -> dict:
    """Run the Week 2 acceptance checks and return machine-readable results."""

    clean_long_gaps = int(
        cleaned["GapFromPrevious_min"].gt(GAP_THRESHOLD_MINUTES).sum()
    )
    segment_count = int(cleaned["SegmentID"].nunique())
    duplicate_events = int(
        cleaned.duplicated(["AnimalID", "Timestamp"]).sum()
    )
    movement_across_boundary = int(
        (
            cleaned["SegmentStart"]
            & (
                cleaned["StepDistance_m"].notna()
                | cleaned["StepTime_s"].notna()
                | cleaned["Speed_mps"].notna()
            )
        ).sum()
    )

    checks = {
        "cleaned_rows": int(len(cleaned)),
        "removed_spikes": int(len(removed)),
        "animal_count": int(cleaned["AnimalID"].nunique()),
        "clean_long_gaps_above_30_minutes": clean_long_gaps,
        "segment_count": segment_count,
        "duplicate_animal_timestamp_events": duplicate_events,
        "missing_required_values": int(cleaned[REQUIRED_COLUMNS].isna().sum().sum()),
        "movement_values_across_segment_boundaries": movement_across_boundary,
        "maximum_speed_mps_after_cleaning": float(cleaned["Speed_mps"].max()),
    }

    expected = {
        "cleaned_rows": EXPECTED_CLEAN_ROWS,
        "removed_spikes": EXPECTED_REMOVED_SPIKES,
        "animal_count": EXPECTED_ANIMALS,
        "clean_long_gaps_above_30_minutes": EXPECTED_CLEAN_LONG_GAPS,
        "segment_count": EXPECTED_SEGMENTS,
        "duplicate_animal_timestamp_events": 0,
        "missing_required_values": 0,
        "movement_values_across_segment_boundaries": 0,
    }
    failures = {
        name: {"observed": checks[name], "expected": expected_value}
        for name, expected_value in expected.items()
        if checks[name] != expected_value
    }
    if failures:
        raise AssertionError(f"Week 2 validation failed: {failures}")
    checks["status"] = "PASS"
    return checks


def export_outputs(
    cleaned: pd.DataFrame,
    removed: pd.DataFrame,
    candidates: pd.DataFrame,
    audit: dict,
    validation: dict,
    animal_summary: pd.DataFrame,
    segment_summary: pd.DataFrame,
    daily_summary: pd.DataFrame,
    projection_summary: pd.DataFrame,
    processed_folder: Path,
    reports_folder: Path,
) -> list[Path]:
    """Export private data tables and public machine-readable summaries."""

    processed_folder.mkdir(parents=True, exist_ok=True)
    reports_folder.mkdir(parents=True, exist_ok=True)

    cleaned_columns = [
        "SourceRowNumber",
        "AnimalID",
        "Species",
        "Timestamp",
        "Year",
        "DayOfYear",
        "Latitude",
        "Longitude",
        "HDOP",
        "RecordsCombined",
        "GapFromPrevious_min",
        "SegmentStart",
        "SegmentNumber",
        "SegmentID",
        "StepTime_s",
        "StepDistance_m",
        "Speed_mps",
        "ElapsedSegment_min",
        "LocalX_m",
        "LocalY_m",
        "LocalEuclideanStep_m",
        "ProjectionDifference_m",
        "ProjectionDifference_percent",
        "Date",
    ]
    cleaned_columns = [column for column in cleaned_columns if column in cleaned.columns]

    paths = [
        processed_folder / "elephant_gps_cleaned_reference.csv",
        processed_folder / "removed_spatial_spikes.csv",
        reports_folder / "week2_spike_candidates.csv",
        reports_folder / "week2_animal_summary.csv",
        reports_folder / "week2_segment_summary.csv",
        reports_folder / "week2_daily_summary.csv",
        reports_folder / "week2_projection_comparison.csv",
        reports_folder / "week2_preprocessing_summary.json",
    ]

    cleaned[cleaned_columns].to_csv(paths[0], index=False, date_format="%Y-%m-%d %H:%M:%S")
    removed.to_csv(paths[1], index=False, date_format="%Y-%m-%d %H:%M:%S")
    candidate_public_columns = [
        "AnimalID",
        "Timestamp",
        "IncomingInterval_min",
        "OutgoingInterval_min",
        "IncomingDistance_m",
        "OutgoingDistance_m",
        "NeighbourBridgeDistance_m",
        "IncomingSpeed_mps",
        "OutgoingSpeed_mps",
        "ScreenRule",
    ]
    candidates[candidate_public_columns].to_csv(
        paths[2], index=False, date_format="%Y-%m-%d %H:%M:%S"
    )
    animal_summary.to_csv(paths[3], index=False)
    segment_summary.to_csv(paths[4], index=False)
    daily_summary.to_csv(paths[5], index=False)
    projection_summary.to_csv(paths[6], index=False)

    summary = {
        "preprocessing_version": "week2_v1",
        "rules": {
            "spike_screen": (
                "incoming adjacent speed > 5 m/s AND outgoing adjacent speed > 5 m/s"
            ),
            "spike_removal": "remove only the six D1-approved AnimalID-timestamp events",
            "segment_boundary": "new segment when within-animal gap > 30 minutes",
            "movement_boundary_rule": "never calculate movement across a segment boundary",
            "complete_day_rule": (
                "at least 95 retained fixes, at least 23.5 hours coverage, one segment"
            ),
            "local_coordinates": (
                "equirectangular x/y metres relative to each animal's first retained fix"
            ),
            "final_geographic_distance": "Haversine distance with Earth radius 6,371,000 m",
        },
        "source_audit": audit,
        "final_validation": validation,
        "complete_days": int(daily_summary["CompleteDay"].sum()),
        "projection_comparison": dict(
            zip(projection_summary["Metric"], projection_summary["Value"], strict=True)
        ),
        "privacy": {
            "raw_workbook_public": False,
            "cleaned_coordinate_table_public": False,
            "removed_coordinate_records_public": False,
            "public_figures_use_absolute_coordinates": False,
        },
    }
    paths[7].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return paths


def run_pipeline(project_root: Path | None = None) -> dict:
    """Run the complete Week 2 preprocessing and EDA pipeline."""

    root = find_project_root(project_root)
    raw_folder = root / "data" / "raw"
    processed_folder = root / "data" / "processed"
    figures_folder = root / "figures"
    reports_folder = root / "reports"
    private_figures_folder = root / "private_figures"

    workbook_path = find_workbook(raw_folder)
    standardised, audit = load_and_standardise(workbook_path)

    if audit["source_rows"] != EXPECTED_RAW_ROWS:
        raise AssertionError(
            f"Expected {EXPECTED_RAW_ROWS} source rows, found {audit['source_rows']}."
        )
    if audit["animal_count"] != EXPECTED_ANIMALS:
        raise AssertionError(
            f"Expected {EXPECTED_ANIMALS} animals, found {audit['animal_count']}."
        )
    if audit["raw_gaps_above_30_minutes"] != EXPECTED_RAW_LONG_GAPS:
        raise AssertionError(
            f"Expected {EXPECTED_RAW_LONG_GAPS} raw long gaps, found "
            f"{audit['raw_gaps_above_30_minutes']}."
        )

    candidates = screen_spike_candidates(standardised)
    plot_candidate_spikes(
        standardised,
        candidates,
        private_figures_folder / "week2_candidate_spike_inspection.png",
    )
    cleaned, removed = remove_approved_spikes(standardised, candidates)
    cleaned = segment_trajectories(cleaned)
    cleaned = add_movement_metrics(cleaned)

    validation = validate_final_outputs(cleaned, removed)
    animal_summary, segment_summary, daily_summary, projection_summary = (
        make_summary_tables(cleaned)
    )
    data_paths = export_outputs(
        cleaned,
        removed,
        candidates,
        audit,
        validation,
        animal_summary,
        segment_summary,
        daily_summary,
        projection_summary,
        processed_folder,
        reports_folder,
    )
    figure_paths = create_eda_figures(cleaned, daily_summary, figures_folder)

    return {
        "project_root": root,
        "workbook": workbook_path,
        "audit": audit,
        "candidates": candidates,
        "cleaned": cleaned,
        "removed": removed,
        "validation": validation,
        "animal_summary": animal_summary,
        "segment_summary": segment_summary,
        "daily_summary": daily_summary,
        "projection_summary": projection_summary,
        "data_paths": data_paths,
        "figure_paths": figure_paths,
    }


def main() -> None:
    """Command-line entry point."""

    result = run_pipeline()
    print("=" * 72)
    print("WEEK 2 PREPROCESSING PASSED")
    print("=" * 72)
    for name, value in result["validation"].items():
        print(f"{name:<48} {value}")
    print("\nPrivate coordinate outputs:")
    for path in result["data_paths"][:2]:
        print(" -", path)
    print("\nReport outputs:")
    for path in result["data_paths"][2:]:
        print(" -", path)
    print("\nPublic figures:")
    for path in result["figure_paths"]:
        print(" -", path)


if __name__ == "__main__":
    main()
