"""Tests for the Week 5 robustness functions."""

import pandas as pd
import pytest

from src import robustness


def sample_per_animal_results():
    """Return a small deterministic validation table."""

    return pd.DataFrame(
        {
            "Method": [
                "linear",
                "linear",
                "linear",
                "linear",
                "pchip",
                "pchip",
                "pchip",
                "pchip",
            ],
            "Interval_min": [
                30,
                30,
                60,
                60,
                30,
                30,
                60,
                60,
            ],
            "AnimalID": [
                "A",
                "B",
                "A",
                "B",
                "A",
                "B",
                "A",
                "B",
            ],
            "MedianPositionError_m": [
                40,
                50,
                70,
                80,
                35,
                45,
                65,
                75,
            ],
            (
                "MedianAbsolutePathError_percent"
            ): [
                7,
                9,
                14,
                16,
                6,
                8,
                13,
                17,
            ],
        }
    )


def test_frozen_requirements_accept_30_minutes():
    """Both methods should pass at 30 minutes."""

    results = (
        robustness.evaluate_per_animal_requirements(
            sample_per_animal_results(),
            position_tolerance_m=100,
            path_tolerance_percent=10,
        )
    )

    thirty = results.loc[
        results["Interval_min"].eq(30)
    ]

    assert thirty["AllAnimalsPass"].all()


def test_frozen_requirements_reject_60_minutes():
    """Both methods should fail the path rule at 60 minutes."""

    results = (
        robustness.evaluate_per_animal_requirements(
            sample_per_animal_results(),
            position_tolerance_m=100,
            path_tolerance_percent=10,
        )
    )

    sixty = results.loc[
        results["Interval_min"].eq(60)
    ]

    assert not sixty["AllAnimalsPass"].any()


def test_non_positive_tolerance_is_rejected():
    """Unsupported tolerances must raise a clear error."""

    with pytest.raises(
        ValueError,
        match="Position tolerance",
    ):
        robustness.evaluate_per_animal_requirements(
            sample_per_animal_results(),
            position_tolerance_m=0,
            path_tolerance_percent=10,
        )