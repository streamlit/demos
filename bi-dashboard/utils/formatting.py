"""Number formatting helpers shared by pages and chart builders."""

from __future__ import annotations


def money(value: float) -> str:
    """Format a dollar amount compactly, for example ``$4.82M`` or ``$812K``."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.2f}M"
    if value >= 10_000:
        return f"{sign}${value / 1_000:.0f}K"
    if value >= 1_000:
        return f"{sign}${value / 1_000:.1f}K"
    return f"{sign}${value:,.0f}"


def money_md(value: float) -> str:
    """Format a dollar amount for Markdown, where a pair of ``$`` starts math."""
    return money(value).replace("$", r"\$")


def signed_pts(value: float) -> str | int:
    """Format a percentage-point change as a delta, using ``0`` when it rounds to zero."""
    return f"{value:+.1f} pts" if round(value, 1) else 0


def change(current: float, previous: float) -> float:
    """Return the relative change between two values, or 0 when undefined."""
    return round(current / previous - 1, 3) if previous else 0.0


def signed_pct(value: float) -> str | int:
    """Format a relative change as a delta, using ``0`` for a flat value."""
    return f"{value:+.1%}" if value else 0
