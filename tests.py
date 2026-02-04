#!/usr/bin/env python3
"""Basic smoke tests for wafer_calculator.

Run: python3 tests.py
"""

import wafer_calculator as wc


def assert_positive(value, label):
    if value <= 0:
        raise AssertionError(f"{label} expected > 0, got {value}")


def run_calculation_cases():
    cases = [
        dict(wafer=100, die_w=10, die_h=10, scribe=0.1, edge=3, flat=32.5, notch=0),
        dict(wafer=150, die_w=20, die_h=15, scribe=0.1, edge=3, flat=47.5, notch=0),
        dict(wafer=200, die_w=10, die_h=10, scribe=0.1, edge=3, flat=0, notch=1.0),
        dict(wafer=300, die_w=10, die_h=10, scribe=0.1, edge=3, flat=0, notch=1.0),
    ]

    for case in cases:
        result = wc.calculate_dies(
            case["wafer"],
            case["die_w"],
            case["die_h"],
            case["scribe"],
            case["edge"],
            case["flat"],
            case["notch"],
            max_positions=0,
            include_partial=True,
        )

        assert_positive(result["usable_radius"], "usable_radius")
        assert result["full_dies"] >= 0
        assert result["partial_dies"] >= 0
        assert result["total_sites"] == result["full_dies"] + result["partial_dies"]


def run_partial_off_case():
    result = wc.calculate_dies(100, 20, 15, 0.1, 3, 32.5, 0, max_positions=0, include_partial=False)
    assert result["partial_dies"] == 0


if __name__ == "__main__":
    run_calculation_cases()
    run_partial_off_case()
    print("All tests passed.")
