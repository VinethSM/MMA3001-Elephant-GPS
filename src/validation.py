"""Week 4 full validation for the elephant GPS sampling project."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from src import reconstruction


# These are the experimental choices frozen during Week 3.
INTERVALS = (30, 60, 120, 240)
POSITION_TOLERANCE_M = 100.0
PATH_TOLERANCE_PERCENT = 10.0

CASE_KEYS = [
    "AnimalID",
    "SegmentID",
    "Interval_min",
    "Offset",
]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 fingerprint of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def selected_methods_from_contract(
    contract: dict,
) -> list[str]:
    """Read and validate the student's frozen D4 method choice."""

    methods = (
        contract
        .get("methods", {})
        .get("full_study_methods", [])
    )

    if not isinstance(methods, list) or len(methods) < 2:
        raise ValueError(
            "Complete D4 in experiment_contract.yaml first."
        )

    if "linear" not in methods:
        raise ValueError(
            "Linear must remain as the baseline."
        )

    if len(methods) != len(set(methods)):
        raise ValueError(
            "The selected method list contains duplicates."
        )

    unsupported = (
        set(methods)
        - set(reconstruction.SUPPORTED_METHODS)
    )

    if unsupported:
        raise ValueError(
            f"Unsupported methods: {sorted(unsupported)}"
        )

    return methods


def common_supported_cases(
    support: pd.DataFrame,
    methods: list[str],
) -> pd.DataFrame:
    """Return cases supported by every selected method."""

    chosen = support.loc[
        support["Method"].isin(methods)
    ].copy()

    common = (
        chosen
        .assign(
            Supported=chosen["Status"].eq("supported")
        )
        .groupby(
            CASE_KEYS,
            as_index=False,
            sort=True,
        )
        .agg(
            SupportingMethods=("Supported", "sum"),
            EligibleWithheld=(
                "EligibleWithheld",
                "first",
            ),
        )
    )

    common = common.loc[
        common["SupportingMethods"].eq(len(methods))
    ].reset_index(drop=True)

    return common


def summarise_points(
    predictions: pd.DataFrame,
    groups: list[str],
) -> pd.DataFrame:
    """Calculate point-error and residual metrics."""

    summary = (
        predictions
        .groupby(
            groups,
            as_index=False,
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
                lambda values: float(
                    values.quantile(0.95)
                ),
            ),
            MaximumPositionError_m=(
                "PositionError_m",
                "max",
            ),
            MedianResidualX_m=(
                "ResidualX_m",
                "median",
            ),
            MedianResidualY_m=(
                "ResidualY_m",
                "median",
            ),
            OvershootCount=(
                "CoordinateOvershoot",
                "sum",
            ),
        )
    )

    summary["OvershootPercent"] = (
        100.0
        * summary["OvershootCount"]
        / summary["PredictedFixes"]
    )

    return summary


def summarise_cases(
    cases: pd.DataFrame,
    groups: list[str],
) -> pd.DataFrame:
    """Calculate path, resource, coverage and runtime metrics."""

    summary = (
        cases
        .groupby(
            groups,
            as_index=False,
            sort=True,
        )
        .agg(
            TotalCases=(
                "Status",
                "size",
            ),
            SuccessfulCases=(
                "Status",
                lambda values: int(
                    values.eq("ok").sum()
                ),
            ),
            MedianSignedPathError_percent=(
                "SignedPathLengthError_percent",
                "median",
            ),
            MedianAbsolutePathError_percent=(
                "AbsolutePathLengthError_percent",
                "median",
            ),
            P95AbsolutePathError_percent=(
                "AbsolutePathLengthError_percent",
                lambda values: float(
                    values.quantile(0.95)
                ),
            ),
            MedianFixReduction_percent=(
                "FixReduction_percent",
                "median",
            ),
            TotalInterpolationRuntime_s=(
                "Runtime_s",
                "sum",
            ),
            MaximumReconstructedSpeed_mps=(
                "MaximumReconstructedSpeed_mps",
                "max",
            ),
        )
    )

    summary["FailedCases"] = (
        summary["TotalCases"]
        - summary["SuccessfulCases"]
    )

    summary["CaseSuccessPercent"] = (
        100.0
        * summary["SuccessfulCases"]
        / summary["TotalCases"]
    )

    return summary


def apply_frozen_criteria(
    summary: pd.DataFrame,
) -> pd.DataFrame:
    """Apply D6: both mandatory criteria must pass."""

    result = summary.copy()

    result["PositionCriterionPass"] = (
        result["MedianPositionError_m"]
        .le(POSITION_TOLERANCE_M)
    )

    result["PathCriterionPass"] = (
        result[
            "MedianAbsolutePathError_percent"
        ]
        .le(PATH_TOLERANCE_PERCENT)
    )

    result["MandatoryCriteriaPass"] = (
        result["PositionCriterionPass"]
        & result["PathCriterionPass"]
    )

    return result


def save_predictions(
    predictions: pd.DataFrame,
    folder: Path,
    method: str,
    interval: int,
) -> Path:
    """Save predictions as Parquet or compressed CSV."""

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    parquet_path = (
        folder
        / f"{method}_{interval}min.parquet"
    )

    try:
        predictions.to_parquet(
            parquet_path,
            index=False,
            compression="snappy",
        )

        return parquet_path

    except ImportError:
        csv_path = (
            folder
            / f"{method}_{interval}min.csv.gz"
        )

        predictions.to_csv(
            csv_path,
            index=False,
            compression="gzip",
            date_format="%Y-%m-%d %H:%M:%S",
        )

        return csv_path


def run_experiment(
    reference: pd.DataFrame,
    methods: list[str],
    prediction_folder: Path,
) -> dict:
    """Run all intervals, offsets and common-supported cases."""

    support = reconstruction.build_support_audit(
        reference,
        INTERVALS,
        methods,
    )

    common = common_supported_cases(
        support,
        methods,
    )

    coverage = (
        support
        .assign(
            Supported=support["Status"].eq(
                "supported"
            )
        )
        .groupby(
            [
                "Method",
                "Interval_min",
            ],
            as_index=False,
        )
        .agg(
            AvailableCases=(
                "Status",
                "size",
            ),
            MethodSupportedCases=(
                "Supported",
                "sum",
            ),
            MethodUsableWithheld=(
                "UsableWithheld",
                "sum",
            ),
        )
    )

    coverage["CaseCoverage_percent"] = (
        100.0
        * coverage["MethodSupportedCases"]
        / coverage["AvailableCases"]
    )

    case_rows = []
    overall_parts = []
    animal_parts = []
    offset_parts = []
    worst_parts = []
    prediction_paths = []

    for interval in INTERVALS:
        common_interval = common.loc[
            common["Interval_min"].eq(interval)
        ]

        for method in methods:
            print(
                f"Running {method:>6} at "
                f"{interval:>3} minutes: "
                f"{len(common_interval)} common cases",
                flush=True,
            )

            frames = []

            for row in common_interval.itertuples(
                index=False
            ):
                predicted, case = (
                    reconstruction.reconstruct_case(
                        reference,
                        row.SegmentID,
                        int(row.Interval_min),
                        int(row.Offset),
                        method,
                    )
                )

                comparable = (
                    case["RetainedAnchors"]
                    + case["EligibleWithheld"]
                )

                case["ComparableFixes"] = comparable

                case["FixReduction_percent"] = (
                    100.0
                    * case["EligibleWithheld"]
                    / comparable
                )

                case_rows.append(case)

                if not predicted.empty:
                    predicted["ResidualX_m"] = (
                        predicted["LocalX_m"]
                        - predicted["EstimatedX_m"]
                    )

                    predicted["ResidualY_m"] = (
                        predicted["LocalY_m"]
                        - predicted["EstimatedY_m"]
                    )

                    frames.append(predicted)

            if not frames:
                raise RuntimeError(
                    f"No predictions produced for "
                    f"{method}, {interval} minutes."
                )

            predictions = (
                pd.concat(
                    frames,
                    ignore_index=True,
                )
                .sort_values(
                    [
                        "AnimalID",
                        "SegmentID",
                        "Offset",
                        "Timestamp",
                    ],
                    kind="mergesort",
                )
                .reset_index(drop=True)
            )

            private_columns = [
                "SourceRowNumber",
                "AnimalID",
                "SegmentID",
                "Timestamp",
                "Method",
                "Interval_min",
                "Offset",
                "LocalX_m",
                "LocalY_m",
                "EstimatedX_m",
                "EstimatedY_m",
                "ResidualX_m",
                "ResidualY_m",
                "PositionError_m",
                "CoordinateOvershoot",
            ]

            saved = save_predictions(
                predictions[private_columns],
                prediction_folder,
                method,
                interval,
            )

            prediction_paths.append(
                str(saved)
            )

            overall_parts.append(
                summarise_points(
                    predictions,
                    [
                        "Method",
                        "Interval_min",
                    ],
                )
            )

            animal_parts.append(
                summarise_points(
                    predictions,
                    [
                        "Method",
                        "Interval_min",
                        "AnimalID",
                    ],
                )
            )

            offset_parts.append(
                summarise_points(
                    predictions,
                    [
                        "Method",
                        "Interval_min",
                        "Offset",
                    ],
                )
            )

            public_worst_columns = [
                "SourceRowNumber",
                "AnimalID",
                "SegmentID",
                "Method",
                "Interval_min",
                "Offset",
                "PositionError_m",
                "CoordinateOvershoot",
            ]

            worst_parts.append(
                predictions
                .nlargest(
                    5,
                    "PositionError_m",
                )[public_worst_columns]
            )

    cases = pd.DataFrame(case_rows)

    overall_points = pd.concat(
        overall_parts,
        ignore_index=True,
    )

    animal_points = pd.concat(
        animal_parts,
        ignore_index=True,
    )

    offset_points = pd.concat(
        offset_parts,
        ignore_index=True,
    )

    overall_cases = summarise_cases(
        cases,
        [
            "Method",
            "Interval_min",
        ],
    )

    animal_cases = summarise_cases(
        cases,
        [
            "Method",
            "Interval_min",
            "AnimalID",
        ],
    )

    offset_cases = summarise_cases(
        cases,
        [
            "Method",
            "Interval_min",
            "Offset",
        ],
    )

    overall = apply_frozen_criteria(
        overall_points.merge(
            overall_cases,
            on=[
                "Method",
                "Interval_min",
            ],
        )
    )

    overall = overall.merge(
        coverage,
        on=[
            "Method",
            "Interval_min",
        ],
    )

    per_animal = apply_frozen_criteria(
        animal_points.merge(
            animal_cases,
            on=[
                "Method",
                "Interval_min",
                "AnimalID",
            ],
        )
    )

    per_offset = apply_frozen_criteria(
        offset_points.merge(
            offset_cases,
            on=[
                "Method",
                "Interval_min",
                "Offset",
            ],
        )
    )

    animal_robustness = (
        per_animal
        .groupby(
            [
                "Method",
                "Interval_min",
            ],
            as_index=False,
        )
        .agg(
            AnimalsEvaluated=(
                "AnimalID",
                "nunique",
            ),
            AnimalsPassingBoth=(
                "MandatoryCriteriaPass",
                "sum",
            ),
            WorstAnimalMedianPositionError_m=(
                "MedianPositionError_m",
                "max",
            ),
            WorstAnimalMedianAbsolutePathError_percent=(
                "MedianAbsolutePathError_percent",
                "max",
            ),
        )
    )

    animal_robustness["AllAnimalsPass"] = (
        animal_robustness[
            "AnimalsPassingBoth"
        ]
        .eq(
            animal_robustness[
                "AnimalsEvaluated"
            ]
        )
    )

    decision = overall.merge(
        animal_robustness,
        on=[
            "Method",
            "Interval_min",
        ],
    )

    decision["FixesRetained_percent"] = (
        100.0
        - decision["MedianFixReduction_percent"]
    )

    return {
        "support": support,
        "common": common,
        "coverage": coverage,
        "cases": cases,
        "overall": overall,
        "per_animal": per_animal,
        "per_offset": per_offset,
        "decision": decision,
        "worst_points": pd.concat(
            worst_parts,
            ignore_index=True,
        ),
        "prediction_paths": prediction_paths,
    }


def main() -> None:
    """Command-line entry point."""

    root = reconstruction.find_project_root()

    reference_path = (
        root
        / "data"
        / "processed"
        / "elephant_gps_cleaned_reference.csv"
    )

    contract_path = (
        root
        / "reports"
        / "experiment_contract.yaml"
    )

    report_folder = root / "reports"

    prediction_folder = (
        root
        / "data"
        / "processed"
        / "week4_predictions"
    )

    reference = reconstruction.load_reference(
        reference_path
    )

    contract = reconstruction.load_contract(
        contract_path
    )

    methods = selected_methods_from_contract(
        contract
    )

    print("WEEK 4 FULL VALIDATION")
    print("Cleaned fixes:", len(reference))
    print(
        "Animals:",
        reference["AnimalID"].nunique(),
    )
    print(
        "Segments:",
        reference["SegmentID"].nunique(),
    )
    print("Methods:", methods)
    print("Intervals:", list(INTERVALS))
    print(
        "Validation population: common_eligible"
    )
    print(
        "Position tolerance (m):",
        POSITION_TOLERANCE_M,
    )
    print(
        "Path tolerance (%):",
        PATH_TOLERANCE_PERCENT,
    )

    results = run_experiment(
        reference,
        methods,
        prediction_folder,
    )

    report_names = {
        "support": "week4_support_audit.csv",
        "common": "week4_common_eligible_cases.csv",
        "coverage": "week4_method_coverage.csv",
        "cases": "week4_case_results.csv",
        "overall": "week4_validation_summary.csv",
        "per_animal": "week4_per_animal_summary.csv",
        "per_offset": "week4_offset_summary.csv",
        "decision": "week4_decision_table.csv",
        "worst_points": "week4_worst_points.csv",
    }

    for key, name in report_names.items():
        results[key].to_csv(
            report_folder / name,
            index=False,
        )

    manifest = {
        "run_timestamp_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "python_version": sys.version,
        "platform": platform.platform(),
        "package_versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "input_reference": str(
            reference_path
        ),
        "input_reference_sha256": (
            sha256_file(reference_path)
        ),
        "experiment_contract": str(
            contract_path
        ),
        "experiment_contract_sha256": (
            sha256_file(contract_path)
        ),
        "methods": methods,
        "intervals_minutes": list(
            INTERVALS
        ),
        "validation_population": (
            "common_eligible"
        ),
        "position_tolerance_m": (
            POSITION_TOLERANCE_M
        ),
        "path_tolerance_percent": (
            PATH_TOLERANCE_PERCENT
        ),
        "common_case_count": int(
            len(results["common"])
        ),
        "method_case_runs": int(
            len(results["cases"])
        ),
        "prediction_partitions": (
            results["prediction_paths"]
        ),
    }

    manifest_path = (
        report_folder
        / "week4_experiment_manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    if not results["cases"]["Status"].eq(
        "ok"
    ).all():
        raise RuntimeError(
            "A pre-screened common case failed."
        )

    print("\nFULL EXPERIMENT COMPLETE")
    print(
        "Common cases:",
        len(results["common"]),
    )
    print(
        "Method-case runs:",
        len(results["cases"]),
    )
    print(
        "Prediction rows:",
        int(
            results["decision"][
                "PredictedFixes"
            ].sum()
        ),
    )
    print(
        "Unexpected failed common cases: 0"
    )

    preview_columns = [
        "Method",
        "Interval_min",
        "MedianPositionError_m",
        "MedianAbsolutePathError_percent",
        "MedianFixReduction_percent",
        "MandatoryCriteriaPass",
        "AnimalsPassingBoth",
        "AnimalsEvaluated",
    ]

    print(
        "\n",
        results["decision"][
            preview_columns
        ]
        .round(3)
        .to_string(index=False),
    )

    print(
        "\nSTOP: inspect the Week 4 "
        "notebook before making D7."
    )


if __name__ == "__main__":
    main()