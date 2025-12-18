"""Utility helpers for the Remeha Home integration."""

from __future__ import annotations


def detect_dhw_setpoint_activity(
    target: float | None,
    comfort: float | None,
    reduced: float | None,
    tolerance: float = 0.25,
) -> str | None:
    """Return 'Comfort', 'Eco', or None based on which setpoint matches or is closest to the target."""
    if (
        comfort is not None
        and target is not None
        and abs(target - comfort) < tolerance
    ):
        return "Comfort"

    if (
        reduced is not None
        and target is not None
        and abs(target - reduced) < tolerance
    ):
        return "Eco"

    # If neither is within tolerance, pick the closest one to avoid flipping
    if target is not None:
        comfort_diff = abs(target - comfort) if comfort is not None else None
        reduced_diff = abs(target - reduced) if reduced is not None else None
        if comfort_diff is not None and reduced_diff is not None:
            return "Comfort" if comfort_diff <= reduced_diff else "Eco"
        if comfort_diff is not None:
            return "Comfort"
        if reduced_diff is not None:
            return "Eco"

    return None
