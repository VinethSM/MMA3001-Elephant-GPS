"""Robustness and tolerance-sensitivity tools.

This module evaluates whether the selected elephant GPS reconstruction
recommendation remains acceptable across animals and under alternative
engineering tolerances.

The module uses the Week 4 validation outputs. It does not rerun the
four-million-row reconstruction experiment.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml


PROJECT_FOLDER = Path(__file__).resolve().parents[1]
REPORTS_FOLDER = PROJECT_FOLDER / "reports"

PER_ANIMAL_FILE = (
    REPORTS_FOLDER
    / "week4_per_animal_summary.csv"
)

FINAL_DECISION_FILE = (
    REPORTS_FOLDER
    / "week4_final_decision.yaml"
)

POSITION_TOLERANCES_M = (
    50.0,
    75.0,
    100.0,
    125.0,
    150.0,
)

PATH_TOLERANCES_PERCENT = (
    5.0,
    10.0,
    15.0,
    20.0,
)


REQUIRED_PER_ANIMAL_COLUMNS = {
    "Method",
    "Interval_min",
    "AnimalID",
    "MedianPositionError_m",
    "MedianAbsolutePathError_percent",
}


def require_columns(
    table: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    """Check that a results table contains required columns.

    Parameters
    ----------
    table
        Table being checked.
    required_columns
        Column names that must be present.
    table_name
        Human-readable table name used in error messages.

    Raises
    ------
    ValueError
        If one or more required columns are absent.
    """

    missing_columns = (
        required_columns
        - set(table.columns)
    )

    if missing_columns:
        raise ValueError(
            f"{table_name} is missing columns: "
            f"{sorted(missing_columns)}"
        )


def evaluate_per_animal_requirements(
    per_animal: pd.DataFrame,
    position_tolerance_m: float,
    path_tolerance_percent: float,
) -> pd.DataFrame:
    """Evaluate method/interval combinations across all animals.

    A combination passes only when every evaluated animal satisfies
    both the positional and path-length requirements.

    Parameters
    ----------
    per_animal
        Week 4 per-animal validation summary.
    position_tolerance_m
        Maximum permitted median position error in metres.
    path_tolerance_percent
        Maximum permitted median absolute path-length error.

    Returns
    -------
    pandas.DataFrame
        One row per method and interval, including the number of
        animals passing both requirements.
    """

    require_columns(
        per_animal,
        REQUIRED_PER_ANIMAL_COLUMNS,
        "Per-animal summary",
    )

    if position_tolerance_m <= 0:
        raise ValueError(
            "Position tolerance must be positive."
        )

    if path_tolerance_percent <= 0:
        raise ValueError(
            "Path tolerance must be positive."
        )

    working = per_animal.copy()

    duplicate_identity = working.duplicated(
        subset=[
            "Method",
            "Interval_min",
            "AnimalID",
        ]
    )

    if duplicate_identity.any():
        raise ValueError(
            "Per-animal summary contains repeated "
            "method-interval-animal rows."
        )

    working["PositionPass"] = (
        working["MedianPositionError_m"]
        <= position_tolerance_m
    )

    working["PathPass"] = (
        working[
            "MedianAbsolutePathError_percent"
        ]
        <= path_tolerance_percent
    )

    working["PassesBoth"] = (
        working["PositionPass"]
        & working["PathPass"]
    )

    evaluated = (
        working.groupby(
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
                "PassesBoth",
                "sum",
            ),
            MaximumAnimalPositionError_m=(
                "MedianPositionError_m",
                "max",
            ),
            MaximumAnimalPathError_percent=(
                "MedianAbsolutePathError_percent",
                "max",
            ),
        )
    )

    evaluated["AllAnimalsPass"] = (
        evaluated["AnimalsPassingBoth"]
        == evaluated["AnimalsEvaluated"]
    )

    evaluated["PositionTolerance_m"] = (
        float(position_tolerance_m)
    )

    evaluated["PathTolerance_percent"] = (
        float(path_tolerance_percent)
    )

    return evaluated.sort_values(
        [
            "Interval_min",
            "Method",
        ]
    ).reset_index(drop=True)


def build_tolerance_sensitivity(
    per_animal: pd.DataFrame,
    selected_method: str,
    position_tolerances_m=(
        POSITION_TOLERANCES_M
    ),
    path_tolerances_percent=(
        PATH_TOLERANCES_PERCENT
    ),
) -> pd.DataFrame:
    """Evaluate alternative tolerance combinations.

    Parameters
    ----------
    per_animal
        Week 4 per-animal validation results.
    selected_method
        Method selected at D7.
    position_tolerances_m
        Positional tolerances to investigate.
    path_tolerances_percent
        Path-length tolerances to investigate.

    Returns
    -------
    pandas.DataFrame
        One row per tolerance combination, containing the longest
        passing interval for the selected method and for any method.
    """

    available_methods = set(
        per_animal["Method"].unique()
    )

    if selected_method not in available_methods:
        raise ValueError(
            f"Selected method {selected_method!r} "
            "does not appear in the results."
        )

    rows = []

    for position_tolerance in (
        position_tolerances_m
    ):
        for path_tolerance in (
            path_tolerances_percent
        ):
            evaluated = (
                evaluate_per_animal_requirements(
                    per_animal,
                    position_tolerance,
                    path_tolerance,
                )
            )

            passing = evaluated.loc[
                evaluated["AllAnimalsPass"]
            ]

            selected_passing = passing.loc[
                passing["Method"].eq(
                    selected_method
                )
            ]

            if passing.empty:
                longest_any = np.nan
                candidates = "none"
            else:
                longest_any = float(
                    passing[
                        "Interval_min"
                    ].max()
                )

                candidate_rows = (
                    passing.sort_values(
                        [
                            "Interval_min",
                            "Method",
                        ]
                    )
                )

                candidates = "; ".join(
                    (
                        candidate_rows["Method"]
                        + "_"
                        + candidate_rows[
                            "Interval_min"
                        ]
                        .astype(int)
                        .astype(str)
                        + "min"
                    ).tolist()
                )

            if selected_passing.empty:
                longest_selected = np.nan
            else:
                longest_selected = float(
                    selected_passing[
                        "Interval_min"
                    ].max()
                )

            rows.append(
                {
                    "PositionTolerance_m": (
                        float(
                            position_tolerance
                        )
                    ),
                    "PathTolerance_percent": (
                        float(path_tolerance)
                    ),
                    (
                        "LongestPassingInterval_"
                        "selected_method_min"
                    ): longest_selected,
                    (
                        "LongestPassingInterval_"
                        "any_method_min"
                    ): longest_any,
                    "PassingCandidates": (
                        candidates
                    ),
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    """Generate Week 5 robustness tables."""

    if not PER_ANIMAL_FILE.exists():
        raise FileNotFoundError(
            f"Missing {PER_ANIMAL_FILE}. "
            "Complete Week 4 first."
        )

    if not FINAL_DECISION_FILE.exists():
        raise FileNotFoundError(
            f"Missing {FINAL_DECISION_FILE}. "
            "Complete D7 first."
        )

    per_animal = pd.read_csv(
        PER_ANIMAL_FILE
    )

    with FINAL_DECISION_FILE.open(
        "r",
        encoding="utf-8",
    ) as stream:
        final_decision = yaml.safe_load(stream)

    selected_method = final_decision[
        "selected_method"
    ]

    selected_interval = int(
        final_decision[
            "selected_interval_minutes"
        ]
    )

    frozen_evaluation = (
        evaluate_per_animal_requirements(
            per_animal,
            position_tolerance_m=100.0,
            path_tolerance_percent=10.0,
        )
    )

    sensitivity = build_tolerance_sensitivity(
        per_animal,
        selected_method=selected_method,
    )

    selected_per_animal = per_animal.loc[
        per_animal["Method"].eq(
            selected_method
        )
        & per_animal["Interval_min"].eq(
            selected_interval
        )
    ].copy()

    selected_per_animal[
        "PositionPass_100m"
    ] = (
        selected_per_animal[
            "MedianPositionError_m"
        ]
        <= 100.0
    )

    selected_per_animal[
        "PathPass_10percent"
    ] = (
        selected_per_animal[
            "MedianAbsolutePathError_percent"
        ]
        <= 10.0
    )

    selected_per_animal[
        "PassesBoth"
    ] = (
        selected_per_animal[
            "PositionPass_100m"
        ]
        & selected_per_animal[
            "PathPass_10percent"
        ]
    )

    frozen_file = (
        REPORTS_FOLDER
        / "week5_frozen_tolerance_evaluation.csv"
    )

    sensitivity_file = (
        REPORTS_FOLDER
        / "week5_tolerance_sensitivity.csv"
    )

    selected_file = (
        REPORTS_FOLDER
        / "week5_selected_per_animal.csv"
    )

    frozen_evaluation.to_csv(
        frozen_file,
        index=False,
    )

    sensitivity.to_csv(
        sensitivity_file,
        index=False,
    )

    selected_per_animal.to_csv(
        selected_file,
        index=False,
    )

    print("WEEK 5 ROBUSTNESS TABLES CREATED")
    print(
        "Selected method:",
        selected_method,
    )
    print(
        "Selected interval:",
        selected_interval,
        "minutes",
    )
    print(
        "Selected animals passing both:",
        int(
            selected_per_animal[
                "PassesBoth"
            ].sum()
        ),
        "/",
        selected_per_animal[
            "AnimalID"
        ].nunique(),
    )
    print(
        "Saved:",
        frozen_file,
    )
    print(
        "Saved:",
        sensitivity_file,
    )
    print(
        "Saved:",
        selected_file,
    )


if __name__ == "__main__":
    main()