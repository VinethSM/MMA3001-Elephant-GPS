"""Reproducible Week 1 audit for the reduced elephant GPS workbook.

Run from the VS Code terminal with:
    python src/data_audit.py

This script audits the raw workbook. It does not delete, repair, or overwrite
any GPS record.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DATASET_FILENAME = "Elephant_GPS_Reduced_60000.xlsx"
GPS_SHEET = "GPS_Data"
EXPECTED_SHEETS = ["GPS_Data", "README", "Sample_Summary", "Data_Dictionary"]
EXPECTED_COLUMNS = [
    "AnimalID",
    "Species",
    "Timestamp",
    "Year",
    "DayOfYear",
    "Latitude",
    "Longitude",
    "HDOP",
    "RecordsCombined",
]
EXPECTED_ROWS = 60_000
EXPECTED_ANIMALS = 6
GAP_THRESHOLD_MINUTES = 30.0
SPIKE_SPEED_THRESHOLD_MPS = 5.0
EARTH_RADIUS_M = 6_371_008.8


def find_project_folder(start: Path | None = None) -> Path:
    """Find the project folder from the terminal or notebook location."""
    starting_places = [
        (start or Path.cwd()).resolve(),
        Path(__file__).resolve().parent,
    ]

    for starting_place in starting_places:
        for candidate in [starting_place, *starting_place.parents]:
            if (candidate / "data" / "raw").is_dir() and (candidate / "src").is_dir():
                return candidate

    raise FileNotFoundError(
        "Could not find a project folder containing data/raw and src. "
        "Open the complete MMA3001_project folder in VS Code."
    )


def haversine_metres(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Return great-circle distance in metres for array-like WGS84 coordinates."""
    lat1 = np.radians(np.asarray(lat1, dtype=float))
    lon1 = np.radians(np.asarray(lon1, dtype=float))
    lat2 = np.radians(np.asarray(lat2, dtype=float))
    lon2 = np.radians(np.asarray(lon2, dtype=float))

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2.0) ** 2
    )
    a = np.clip(a, 0.0, 1.0)

    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def build_data_dictionary() -> pd.DataFrame:
    """Create the project data dictionary for the supplied GPS fields."""
    return pd.DataFrame(
        [
            ["AnimalID", "text", "none", "Unique collared-elephant identifier", "Group trajectories"],
            ["Species", "text", "none", "Species label; elephant in this subset", "Validation/metadata only"],
            ["Timestamp", "datetime", "local time, UTC+02:00", "Time of GPS fix", "Order and downsample trajectories"],
            ["Year", "integer", "year", "Calendar year", "Cross-check Timestamp"],
            ["DayOfYear", "integer", "1-366", "Day number within year", "Cross-check Timestamp"],
            ["Latitude", "number", "WGS84 decimal degrees", "North/south coordinate", "Trajectory reconstruction"],
            ["Longitude", "number", "WGS84 decimal degrees", "East/west coordinate", "Trajectory reconstruction"],
            ["HDOP", "number", "dimensionless", "Horizontal dilution of precision", "Audit only; constant zero here"],
            ["RecordsCombined", "integer", "count >= 1", "Source rows consolidated into this fix", "Cleaning traceability"],
        ],
        columns=["field", "type", "unit_or_format", "meaning", "project_use"],
    )


def audit_workbook(project_folder: Path | None = None) -> dict[str, object]:
    """Audit the raw workbook and save Week 1 audit outputs."""
    project_folder = (project_folder or find_project_folder()).resolve()
    raw_folder = project_folder / "data" / "raw"
    processed_folder = project_folder / "data" / "processed"
    reports_folder = project_folder / "reports"
    figures_folder = project_folder / "figures"

    processed_folder.mkdir(parents=True, exist_ok=True)
    reports_folder.mkdir(parents=True, exist_ok=True)
    figures_folder.mkdir(parents=True, exist_ok=True)

    workbook_path = raw_folder / DATASET_FILENAME
    if not workbook_path.exists():
        raise FileNotFoundError(
            f"Expected workbook not found: {workbook_path}\n"
            "Check its name and make sure it is inside data/raw."
        )

    file_inventory = pd.DataFrame(
        [
            {
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "size_mb": round(path.stat().st_size / 1024**2, 3),
            }
            for path in sorted(raw_folder.iterdir())
            if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".csv"}
        ]
    )

    excel_file = pd.ExcelFile(workbook_path, engine="openpyxl")
    sheet_names = excel_file.sheet_names

    gps_raw = pd.read_excel(workbook_path, sheet_name=GPS_SHEET, engine="openpyxl")

    sheet_inventory_rows = []
    for sheet_name in sheet_names:
        if sheet_name == GPS_SHEET:
            sheet_data = gps_raw
        else:
            sheet_data = pd.read_excel(
                workbook_path,
                sheet_name=sheet_name,
                engine="openpyxl",
            )
        sheet_inventory_rows.append(
            {
                "sheet_name": sheet_name,
                "rows_read_by_pandas": len(sheet_data),
                "columns_read_by_pandas": len(sheet_data.columns),
            }
        )
    sheet_inventory = pd.DataFrame(sheet_inventory_rows)

    missingness = pd.DataFrame(
        {
            "field": gps_raw.columns,
            "missing_count": gps_raw.isna().sum().values,
            "missing_percent": (gps_raw.isna().mean().values * 100).round(4),
        }
    )

    gps = gps_raw.copy()
    gps["SourceExcelRow"] = np.arange(2, len(gps) + 2)
    gps["Timestamp"] = pd.to_datetime(gps["Timestamp"], errors="coerce")

    numeric_fields = [
        "Year",
        "DayOfYear",
        "Latitude",
        "Longitude",
        "HDOP",
        "RecordsCombined",
    ]
    for field in numeric_fields:
        gps[field] = pd.to_numeric(gps[field], errors="coerce")

    gps = gps.sort_values(["AnimalID", "Timestamp"]).reset_index(drop=True)

    duplicate_identity_count = int(
        gps.duplicated(subset=["AnimalID", "Timestamp"], keep=False).sum()
    )
    invalid_latitude_count = int(
        (gps["Latitude"].notna() & ~gps["Latitude"].between(-90, 90)).sum()
    )
    invalid_longitude_count = int(
        (gps["Longitude"].notna() & ~gps["Longitude"].between(-180, 180)).sum()
    )
    timestamp_parse_failures = int(gps["Timestamp"].isna().sum())

    year_mismatch_count = int(
        (
            gps["Timestamp"].notna()
            & gps["Year"].notna()
            & (gps["Year"] != gps["Timestamp"].dt.year)
        ).sum()
    )
    day_of_year_mismatch_count = int(
        (
            gps["Timestamp"].notna()
            & gps["DayOfYear"].notna()
            & (gps["DayOfYear"] != gps["Timestamp"].dt.dayofyear)
        ).sum()
    )

    gps["GapMinutes"] = (
        gps.groupby("AnimalID", observed=True)["Timestamp"]
        .diff()
        .dt.total_seconds()
        .div(60.0)
    )

    positive_gaps = gps.loc[gps["GapMinutes"] > 0, "GapMinutes"]
    modal_gap_minutes = float(positive_gaps.mode().iloc[0])
    median_gap_minutes = float(positive_gaps.median())
    maximum_gap_minutes = float(positive_gaps.max())

    long_gaps = gps.loc[
        gps["GapMinutes"] > GAP_THRESHOLD_MINUTES,
        ["AnimalID", "Timestamp", "GapMinutes", "SourceExcelRow"],
    ].copy()

    gap_frequency = (
        positive_gaps.value_counts()
        .sort_index()
        .rename_axis("gap_minutes")
        .reset_index(name="count")
    )

    grouped = gps.groupby("AnimalID", observed=True, sort=False)
    previous_latitude = grouped["Latitude"].shift(1)
    previous_longitude = grouped["Longitude"].shift(1)
    previous_timestamp = grouped["Timestamp"].shift(1)
    next_latitude = grouped["Latitude"].shift(-1)
    next_longitude = grouped["Longitude"].shift(-1)
    next_timestamp = grouped["Timestamp"].shift(-1)

    incoming_distance_m = haversine_metres(
        previous_latitude,
        previous_longitude,
        gps["Latitude"],
        gps["Longitude"],
    )
    outgoing_distance_m = haversine_metres(
        gps["Latitude"],
        gps["Longitude"],
        next_latitude,
        next_longitude,
    )

    incoming_seconds = (gps["Timestamp"] - previous_timestamp).dt.total_seconds()
    outgoing_seconds = (next_timestamp - gps["Timestamp"]).dt.total_seconds()

    gps["IncomingSpeed_mps"] = np.where(
        incoming_seconds > 0,
        incoming_distance_m / incoming_seconds,
        np.nan,
    )
    gps["OutgoingSpeed_mps"] = np.where(
        outgoing_seconds > 0,
        outgoing_distance_m / outgoing_seconds,
        np.nan,
    )

    candidate_spike_mask = (
        (gps["IncomingSpeed_mps"] > SPIKE_SPEED_THRESHOLD_MPS)
        & (gps["OutgoingSpeed_mps"] > SPIKE_SPEED_THRESHOLD_MPS)
    )

    candidate_spikes = gps.loc[
        candidate_spike_mask,
        [
            "SourceExcelRow",
            "AnimalID",
            "Timestamp",
            "Latitude",
            "Longitude",
            "GapMinutes",
            "IncomingSpeed_mps",
            "OutgoingSpeed_mps",
        ],
    ].copy()

    candidate_spikes["IncomingSpeed_mps"] = candidate_spikes[
        "IncomingSpeed_mps"
    ].round(3)
    candidate_spikes["OutgoingSpeed_mps"] = candidate_spikes[
        "OutgoingSpeed_mps"
    ].round(3)

    animal_coverage = (
        gps.groupby("AnimalID", observed=True)
        .agg(
            rows=("AnimalID", "size"),
            start_timestamp=("Timestamp", "min"),
            end_timestamp=("Timestamp", "max"),
            latitude_min=("Latitude", "min"),
            latitude_max=("Latitude", "max"),
            longitude_min=("Longitude", "min"),
            longitude_max=("Longitude", "max"),
            gaps_above_30_minutes=(
                "GapMinutes",
                lambda series: int((series > GAP_THRESHOLD_MINUTES).sum()),
            ),
        )
        .reset_index()
    )
    animal_coverage["coverage_days"] = (
        animal_coverage["end_timestamp"] - animal_coverage["start_timestamp"]
    ).dt.total_seconds() / 86_400.0
    animal_coverage["coverage_days"] = animal_coverage["coverage_days"].round(2)

    actual_columns = list(gps_raw.columns)
    checks = [
        ["Required sheet names", str(EXPECTED_SHEETS), str(sheet_names), sheet_names == EXPECTED_SHEETS],
        ["GPS row count", EXPECTED_ROWS, len(gps_raw), len(gps_raw) == EXPECTED_ROWS],
        ["GPS column names", str(EXPECTED_COLUMNS), str(actual_columns), actual_columns == EXPECTED_COLUMNS],
        ["Unique AnimalID count", EXPECTED_ANIMALS, gps["AnimalID"].nunique(), gps["AnimalID"].nunique() == EXPECTED_ANIMALS],
        ["Rows per animal", "10,000 each", str(sorted(gps["AnimalID"].value_counts().tolist())), bool((gps["AnimalID"].value_counts() == 10_000).all())],
        ["Missing cells", 0, int(gps_raw.isna().sum().sum()), int(gps_raw.isna().sum().sum()) == 0],
        ["Timestamp parse failures", 0, timestamp_parse_failures, timestamp_parse_failures == 0],
        ["Duplicate AnimalID + Timestamp rows", 0, duplicate_identity_count, duplicate_identity_count == 0],
        ["Invalid latitude values", 0, invalid_latitude_count, invalid_latitude_count == 0],
        ["Invalid longitude values", 0, invalid_longitude_count, invalid_longitude_count == 0],
        ["Year/Timestamp mismatches", 0, year_mismatch_count, year_mismatch_count == 0],
        ["DayOfYear/Timestamp mismatches", 0, day_of_year_mismatch_count, day_of_year_mismatch_count == 0],
        ["Modal positive interval (minutes)", 15.0, modal_gap_minutes, modal_gap_minutes == 15.0],
        ["Median positive interval (minutes)", 15.0, median_gap_minutes, median_gap_minutes == 15.0],
        ["Gaps above 30 minutes", 70, len(long_gaps), len(long_gaps) == 70],
        ["Candidate spatial spikes", 6, len(candidate_spikes), len(candidate_spikes) == 6],
    ]
    audit_summary = pd.DataFrame(
        checks,
        columns=["check", "expected", "actual", "passed"],
    )
    audit_summary["status"] = np.where(audit_summary["passed"], "PASS", "CHECK")

    data_dictionary = build_data_dictionary()

    file_inventory.to_csv(reports_folder / "file_inventory.csv", index=False)
    sheet_inventory.to_csv(reports_folder / "workbook_sheets.csv", index=False)
    data_dictionary.to_csv(reports_folder / "data_dictionary.csv", index=False)
    animal_coverage.to_csv(reports_folder / "animal_coverage.csv", index=False)
    missingness.to_csv(reports_folder / "missingness.csv", index=False)
    gap_frequency.to_csv(reports_folder / "time_gap_frequency.csv", index=False)
    long_gaps.to_csv(reports_folder / "gaps_above_30_minutes.csv", index=False)
    audit_summary.to_csv(reports_folder / "audit_summary.csv", index=False)

    # This private file contains exact animal coordinates and is therefore kept
    # under data/processed, which .gitignore excludes from public GitHub.
    candidate_spikes.to_csv(
        processed_folder / "week1_candidate_spatial_spikes.csv",
        index=False,
    )

    contract_text = f"""# Engineering contract: elephant GPS sampling project

## Engineering question

Which simulated GPS sampling interval minimises the number of collar fixes while
keeping elephant movement-path reconstruction within the provisional accuracy
limits, and how does cubic-spline interpolation compare with linear interpolation?

## Primary inputs

- `AnimalID`: one of the six audited elephant identifiers.
- `Timestamp`: parseable local GPS time (UTC+02:00), ordered within each animal.
- `Latitude`: WGS84 decimal degrees in the audited spatial domain.
- `Longitude`: WGS84 decimal degrees in the audited spatial domain.
- `sampling_interval_minutes`: one of 30, 60, 120, or 240 minutes.
- `method`: linear interpolation baseline or cubic-spline alternative.

`Species`, `Year`, `DayOfYear`, `HDOP`, and `RecordsCombined` are retained for
metadata or audit checks. They are not primary predictors.

## Required outputs

- Reconstructed latitude and longitude at deliberately omitted timestamps.
- Pointwise position error in metres.
- Median, RMSE, and 95th-percentile position error.
- Absolute percentage error in reconstructed total path length.
- Percentage reduction in GPS fixes.
- Runtime for each interval and method.
- Longest interval that passes the approved tolerance.

## Supported domain

- Workbook schema and six AnimalIDs verified by the Week 1 audit.
- Timestamps from {gps['Timestamp'].min()} to {gps['Timestamp'].max()}.
- Observed latitude from {gps['Latitude'].min():.5f} to {gps['Latitude'].max():.5f} degrees.
- Observed longitude from {gps['Longitude'].min():.5f} to {gps['Longitude'].max():.5f} degrees.
- Coordinate validity: latitude -90 to 90; longitude -180 to 180.
- Tested intervals: 30, 60, 120, and 240 minutes, all multiples of the 15-minute reference interval.
- Interpolation only inside a continuous trajectory segment. Do not interpolate
  across a source gap above {GAP_THRESHOLD_MINUTES:.0f} minutes and do not extrapolate beyond segment ends.

## Provisional acceptance limits

- Median reconstruction error <= 100 metres.
- Absolute total path-length error <= 10 percent.
- Always report the 95th-percentile error even though it has no initial pass/fail threshold.
- Treat these as initial engineering assumptions and perform sensitivity analysis later.

## Intended engineering use

Compare tracking detail against the number of required GPS fixes so that a
defensible collar sampling schedule can be recommended for these data.

## Unsupported uses and claims

- Do not claim an exact battery-life increase: the workbook has no power/current data.
- Do not claim future movement prediction: this is reconstruction of withheld points.
- Do not claim the 15-minute reference is the elephant's exact continuous path.
- Do not generalise results to every elephant or every location.
- Do not interpolate across long source gaps.
- Do not use HDOP as a quality predictor here because it is constant at zero.
"""
    (reports_folder / "project_contract.md").write_text(contract_text, encoding="utf-8")

    provenance_text = """# Dataset provenance

## Official source

Hutchinson, Matthew; Walker, Hallie; Abraham, Joel et al. (2026).
*Ecology of community reassembly: Movements and diets of megafauna during a
decade of restoration in Mozambique* [Dataset]. Dryad.
https://doi.org/10.5061/dryad.m905qfv85

Original GPS table: `GPS-COLLAR-LOCATION-RECORDS_ELEPHANT.csv` in `DataS1.zip`.

The official Dryad record reports 839,947 elephant GPS fixes from 18 individuals.
The reduced workbook README reports 839,746 source rows. This 201-row provenance
difference must be recorded rather than silently hidden; it does not alter the
audited 60,000-row reduced workbook.

The official source documents WGS84 decimal-degree coordinates and local GPS
timestamps in UTC+02:00.

## How this reduced workbook was produced

- Six elephants with a nominal 15-minute collar schedule were retained.
- A dense block of 10,000 consecutive fixes was retained per elephant.
- Total reduced size: 60,000 rows.
- The source latitude/longitude fields for the retained LOAF-18 rows were reversed;
  the workbook swapped them to the correct approximately 19 degrees south,
  34 degrees east positions.
- Repeated AnimalID + Timestamp source rows were consolidated with median coordinates.
- `RecordsCombined` records how many source rows were consolidated.
- `DOP` was removed because it was entirely missing.
- `HDOP` was retained for traceability but is constant at zero in this subset.
- Random sampling was not used because it would destroy trajectory order.

## Licence and citation

Dryad publishes datasets under the Creative Commons Zero (CC0) Public Domain
Dedication. Reuse and modification are permitted. The dataset will still be
cited in the report, README, and presentation as scholarly attribution.
"""
    (reports_folder / "data_provenance.md").write_text(provenance_text, encoding="utf-8")

    data_use_text = """# Data-use and location-sensitivity statement

This project uses publicly released historic elephant GPS data from Dryad and
contains no human personal data. CC0 permits reuse; however, exact wildlife
locations can still be sensitive in practice. The exact-coordinate workbook and
all coordinate-bearing processed files will therefore be excluded from the
public GitHub repository. The public repository will contain the DOI, citation,
download/reduction instructions, code, tests, non-sensitive aggregate results,
and documentation. Public maps will be aggregated, rounded, or omitted if exact
locations are unnecessary.
"""
    (reports_folder / "data_use_statement.md").write_text(data_use_text, encoding="utf-8")

    summary_lines = [
        "WEEK 1 ELEPHANT GPS DATA AUDIT",
        "",
        f"Workbook: {workbook_path.name}",
        f"File size: {workbook_path.stat().st_size / 1024**2:.3f} MB",
        f"Sheets: {', '.join(sheet_names)}",
        f"GPS rows: {len(gps_raw):,}",
        f"GPS fields: {', '.join(actual_columns)}",
        f"Animal IDs: {gps['AnimalID'].nunique()}",
        f"Timestamp range: {gps['Timestamp'].min()} to {gps['Timestamp'].max()}",
        f"Latitude range: {gps['Latitude'].min():.5f} to {gps['Latitude'].max():.5f}",
        f"Longitude range: {gps['Longitude'].min():.5f} to {gps['Longitude'].max():.5f}",
        f"Missing cells: {int(gps_raw.isna().sum().sum())}",
        f"Duplicate AnimalID + Timestamp rows: {duplicate_identity_count}",
        f"Modal positive interval: {modal_gap_minutes:.1f} minutes",
        f"Median positive interval: {median_gap_minutes:.1f} minutes",
        f"Maximum source gap: {maximum_gap_minutes:.1f} minutes",
        f"Source gaps above 30 minutes: {len(long_gaps)}",
        f"Candidate spatial spikes for inspection: {len(candidate_spikes)}",
        "",
        "Candidate spikes were flagged for inspection only. No raw row was deleted.",
    ]
    (reports_folder / "week1_audit.txt").write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )

    return {
        "project_folder": project_folder,
        "workbook_path": workbook_path,
        "file_inventory": file_inventory,
        "sheet_names": sheet_names,
        "sheet_inventory": sheet_inventory,
        "gps_raw": gps_raw,
        "gps_audit": gps,
        "data_dictionary": data_dictionary,
        "missingness": missingness,
        "animal_coverage": animal_coverage,
        "gap_frequency": gap_frequency,
        "long_gaps": long_gaps,
        "candidate_spikes": candidate_spikes,
        "audit_summary": audit_summary,
        "modal_gap_minutes": modal_gap_minutes,
        "median_gap_minutes": median_gap_minutes,
        "maximum_gap_minutes": maximum_gap_minutes,
        "duplicate_identity_count": duplicate_identity_count,
        "invalid_latitude_count": invalid_latitude_count,
        "invalid_longitude_count": invalid_longitude_count,
        "year_mismatch_count": year_mismatch_count,
        "day_of_year_mismatch_count": day_of_year_mismatch_count,
    }


def main() -> None:
    """Run the audit from a terminal and print the important result."""
    results = audit_workbook()
    print("\nWEEK 1 AUDIT RESULTS\n")
    print(results["audit_summary"].to_string(index=False))
    print("\nSaved reports in:", results["project_folder"] / "reports")
    print(
        "Saved private spike candidates in:",
        results["project_folder"] / "data" / "processed",
    )

    failed_checks = results["audit_summary"].loc[
        ~results["audit_summary"]["passed"]
    ]
    if not failed_checks.empty:
        raise SystemExit(
            "\nOne or more checks need investigation. Do not continue to Week 2 yet."
        )

    print("\nWEEK 1 AUDIT PASSED. No raw data was changed.")


if __name__ == "__main__":
    main()
