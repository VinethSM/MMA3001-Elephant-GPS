"""Run a quick de-identified demonstration of the selected solution.

This demonstration applies the final PCHIP 30-minute configuration to
one sufficiently long trajectory segment. It uses the genuine project
functions but is not a replacement for the full validation experiment.
"""

from __future__ import annotations

import pandas as pd

from src import reconstruction


REFERENCE_RELATIVE_PATH = (
    "data/processed/"
    "elephant_gps_cleaned_reference.csv"
)

FINAL_METHOD = "pchip"
FINAL_INTERVAL_MINUTES = 30
MINIMUM_DEMO_FIXES = 20


def select_demo_segment(
    reference: pd.DataFrame,
    minimum_fixes: int = MINIMUM_DEMO_FIXES,
) -> str:
    """Select a sufficiently long segment for the quick demonstration.

    Parameters
    ----------
    reference
        Cleaned GPS reference dataset.
    minimum_fixes
        Minimum number of observations required in the segment.

    Returns
    -------
    str
        Identifier of the longest eligible segment.

    Raises
    ------
    ValueError
        If no segment contains the required number of observations.
    """

    segment_sizes = reference.groupby(
        "SegmentID",
        sort=True,
    ).size()

    eligible = segment_sizes.loc[
        segment_sizes.ge(minimum_fixes)
    ]

    if eligible.empty:
        raise ValueError(
            "No segment is long enough for the demonstration."
        )

    return str(eligible.idxmax())


def run_demo(
    reference: pd.DataFrame,
) -> pd.DataFrame:
    """Run PCHIP 30-minute reconstruction for every valid offset.

    Parameters
    ----------
    reference
        Cleaned GPS reference dataset.

    Returns
    -------
    pandas.DataFrame
        De-identified accuracy summary for the demonstration segment.
    """

    segment_id = select_demo_segment(
        reference
    )

    stride = reconstruction.interval_to_stride(
        FINAL_INTERVAL_MINUTES
    )

    rows = []

    for offset in range(stride):
        _, case = reconstruction.reconstruct_case(
            reference=reference,
            segment_id=segment_id,
            interval_minutes=(
                FINAL_INTERVAL_MINUTES
            ),
            offset=offset,
            method=FINAL_METHOD,
        )

        if case["Status"] != "ok":
            continue

        fix_reduction = (
            100.0
            * (
                case["SegmentFixes"]
                - case["RetainedAnchors"]
            )
            / case["SegmentFixes"]
        )

        rows.append(
            {
                "Method": FINAL_METHOD,
                "Interval_min": (
                    FINAL_INTERVAL_MINUTES
                ),
                "Offset": offset,
                "RetainedAnchors": (
                    case["RetainedAnchors"]
                ),
                "WithheldFixes": (
                    case["EligibleWithheld"]
                ),
                "MedianError_m": (
                    case["MedianError_m"]
                ),
                "P95Error_m": (
                    case["P95Error_m"]
                ),
                "AbsolutePathError_percent": (
                    case[
                        "AbsolutePathLengthError_percent"
                    ]
                ),
                "FixReduction_percent": (
                    fix_reduction
                ),
                "CoordinateOvershoots": (
                    case[
                        "CoordinateOvershootCount"
                    ]
                ),
            }
        )

    if not rows:
        raise RuntimeError(
            "No supported demonstration cases were produced."
        )

    return pd.DataFrame(rows)


def main() -> None:
    """Load the reference data and print the quick demonstration."""

    project_root = (
        reconstruction.find_project_root()
    )

    reference_file = (
        project_root
        / REFERENCE_RELATIVE_PATH
    )

    if not reference_file.exists():
        raise FileNotFoundError(
            "Cleaned reference data was not found at "
            f"{reference_file}. Run preprocessing first."
        )

    reference = reconstruction.load_reference(
        reference_file
    )

    results = run_demo(reference)

    print("=" * 70)
    print("ELEPHANT GPS QUICK DEMONSTRATION")
    print("=" * 70)
    print(
        "Configuration: PCHIP reconstruction, "
        "30-minute sampling"
    )
    print(
        "This is a short demonstration on one segment, "
        "not the full validation study."
    )
    print()

    print(
        results.round(3).to_string(
            index=False
        )
    )

    print()
    print(
        "Full-study result: 39.632 m median position "
        "error, 7.907% median absolute path error and "
        "49.894% median fix reduction."
    )


if __name__ == "__main__":
    main()
    