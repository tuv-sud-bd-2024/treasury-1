"""
Money Market Module – Interest Calculation Utilities

Implements standard day-count conventions used in money markets:
  • ACT/365  – actual days / 365
  • ACT/360  – actual days / 360
  • 30/360   – 30-day month convention / 360
"""

from decimal import Decimal, ROUND_HALF_UP
import datetime


def calculate_days(
    start_date: datetime.date,
    end_date: datetime.date,
    convention: str,
) -> int:
    """
    Return the number of days between *start_date* and *end_date* using the
    given day-count convention.

    For ACT/365 and ACT/360 the result is simply the calendar difference.
    For 30/360 each month is treated as 30 days.
    """
    if convention == "30/360":
        d1 = min(start_date.day, 30)
        d2 = min(end_date.day, 30) if d1 == 30 else end_date.day
        return (
            360 * (end_date.year - start_date.year)
            + 30 * (end_date.month - start_date.month)
            + (d2 - d1)
        )
    # ACT/365 and ACT/360 both use calendar days in the numerator
    return (end_date - start_date).days


def _year_fraction(days: int, convention: str) -> Decimal:
    """Convert a day count to a year fraction based on the convention."""
    if convention == "ACT/360":
        return Decimal(days) / Decimal("360")
    # ACT/365 and 30/360 both use 365 as denominator
    return Decimal(days) / Decimal("365")


def calculate_interest(
    principal: Decimal,
    rate: Decimal,
    days: int,
    convention: str,
) -> Decimal:
    """
    Compute simple interest:  I = P × r × (days / year_basis)

    Returns the result rounded to 2 decimal places (ROUND_HALF_UP).
    """
    year_fraction = _year_fraction(days, convention)
    interest = principal * rate * year_fraction
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_maturity_amount(
    principal: Decimal,
    rate: Decimal,
    days: int,
    convention: str,
) -> Decimal:
    """Return principal plus interest at maturity."""
    return principal + calculate_interest(principal, rate, days, convention)
