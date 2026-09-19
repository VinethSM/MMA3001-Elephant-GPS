import numpy as np
import pandas as pd
import pytest

from src import validation


def test_common_supported_cases_uses_intersection():
    support = pd.DataFrame(
        [
            [
                "E1",
                "S1",
                30,
                0,
                "linear",
                4,
                4,
                "supported",
            ],
            [
                "E1",
                "S1",
                30,
                0,
                "cubic",
                4,
                4,
                "supported",
            ],
            [
                "E1",
                "S1",
                30,
                0,
                "pchip",
                4,
                4,
                "supported",
            ],
            [
                "E1",
                "S2",
                30,
                0,
                "linear",
                2,
                2,
                "supported",
            ],
            [
                "E1",
                "S2",
                30,
                0,
                "cubic",
                2,
                0,
                "insufficient_anchors",
            ],
            [
                "E1",
                "S2",
                30,
                0,
                "pchip",
                2,
                2,
                "supported",
            ],
        ],
        columns=[
            "AnimalID",
            "SegmentID",
            "Interval_min",
            "Offset",
            "Method",
            "EligibleWithheld",
            "UsableWithheld",
            "Status",
        ],
    )

    common = validation.common_supported_cases(
        support,
        [
            "linear",
            "cubic",
            "pchip",
        ],
    )

    assert common["SegmentID"].tolist() == [
        "S1"
    ]


def test_point_metrics_are_calculated_correctly():
    predictions = pd.DataFrame(
        {
            "Method": ["linear"] * 4,
            "Interval_min": [60] * 4,
            "PositionError_m": [
                0.0,
                10.0,
                20.0,
                30.0,
            ],
            "ResidualX_m": [
                -2.0,
                -1.0,
                1.0,
                2.0,
            ],
            "ResidualY_m": [
                0.0,
                0.0,
                0.0,
                0.0,
            ],
            "CoordinateOvershoot": [
                False,
                False,
                False,
                False,
            ],
        }
    )

    summary = validation.summarise_points(
        predictions,
        [
            "Method",
            "Interval_min",
        ],
    ).iloc[0]

    assert (
        summary["MedianPositionError_m"]
        == pytest.approx(15.0)
    )

    assert (
        summary["MAE_m"]
        == pytest.approx(15.0)
    )

    assert (
        summary["RMSE_m"]
        == pytest.approx(np.sqrt(350.0))
    )

    assert (
        summary["OvershootPercent"]
        == pytest.approx(0.0)
    )


def test_acceptance_requires_both_criteria():
    summary = pd.DataFrame(
        {
            "MedianPositionError_m": [
                90.0,
                90.0,
                110.0,
            ],
            "MedianAbsolutePathError_percent": [
                9.0,
                11.0,
                9.0,
            ],
        }
    )

    result = (
        validation.apply_frozen_criteria(
            summary
        )
    )

    assert (
        result[
            "MandatoryCriteriaPass"
        ].tolist()
        == [
            True,
            False,
            False,
        ]
    )


def test_contract_requires_linear_baseline():
    methods = (
        validation.selected_methods_from_contract(
            {
                "methods": {
                    "full_study_methods": [
                        "linear",
                        "pchip",
                    ]
                }
            }
        )
    )

    assert methods == [
        "linear",
        "pchip",
    ]

    with pytest.raises(
        ValueError,
        match="Linear",
    ):
        validation.selected_methods_from_contract(
            {
                "methods": {
                    "full_study_methods": [
                        "cubic",
                        "pchip",
                    ]
                }
            }
        )