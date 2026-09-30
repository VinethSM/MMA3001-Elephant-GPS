"""Convert a binary cProfile result into readable reports."""

from __future__ import annotations

import json
from pathlib import Path
import pstats


PROJECT_FOLDER = Path(__file__).resolve().parents[1]
REPORTS_FOLDER = PROJECT_FOLDER / "reports"

PROFILE_FILE = (
    REPORTS_FOLDER
    / "week5_validation_before.prof"
)

TEXT_FILE = (
    REPORTS_FOLDER
    / "week5_profile_before.txt"
)

SUMMARY_FILE = (
    REPORTS_FOLDER
    / "week5_profile_before_summary.json"
)


def main() -> None:
    """Create text and JSON summaries of a cProfile run."""

    if not PROFILE_FILE.exists():
        raise FileNotFoundError(
            f"Cannot find {PROFILE_FILE}. "
            "Run cProfile first."
        )

    stats = pstats.Stats(
        str(PROFILE_FILE)
    )

    summary = {
        "total_function_calls": (
            stats.total_calls
        ),
        "primitive_function_calls": (
            stats.prim_calls
        ),
        "total_profiled_seconds": (
            stats.total_tt
        ),
    }

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(
            summary,
            stream,
            indent=2,
        )

    with TEXT_FILE.open(
        "w",
        encoding="utf-8",
    ) as stream:
        stream.write(
            "WEEK 5 VALIDATION PROFILE\n"
        )
        stream.write(
            "=" * 70
            + "\n\n"
        )
        stream.write(
            json.dumps(
                summary,
                indent=2,
            )
        )
        stream.write(
            "\n\nTOP 50 FUNCTIONS BY "
            "CUMULATIVE TIME\n"
        )
        stream.write(
            "=" * 70
            + "\n"
        )

        cumulative_stats = pstats.Stats(
            str(PROFILE_FILE),
            stream=stream,
        )

        cumulative_stats.sort_stats(
            "cumulative"
        ).print_stats(50)

        stream.write(
            "\n\nPROJECT FUNCTIONS\n"
        )
        stream.write(
            "=" * 70
            + "\n"
        )

        project_stats = pstats.Stats(
            str(PROFILE_FILE),
            stream=stream,
        )

        project_stats.sort_stats(
            "cumulative"
        ).print_stats(
            (
                "validation.py|"
                "reconstruction.py"
            )
        )

    print("PROFILE REPORT CREATED")
    print("Profiled seconds:", stats.total_tt)
    print("Saved:", TEXT_FILE)
    print("Saved:", SUMMARY_FILE)


if __name__ == "__main__":
    main()