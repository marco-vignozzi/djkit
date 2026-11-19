"""
Monthly and yearly date helpers.

Pure functions (no database, no Django imports) for recurring schedules such
as installments, subscriptions, recurring invoices or yearly renewals.

Rule of monthly_due_dates:
    - the first date is the start date;
    - the following ones every month on the same day of the month;
    - a day that does not exist in a month (29, 30, 31) is moved to the last
      day of that month, without affecting the following months
      (31 Jan -> 28 Feb -> 31 Mar);
    - only dates up to the end date (inclusive) are produced.
"""

import calendar
from datetime import date


def clamped_date(year: int, month: int, day: int) -> date:
    """
    Build a date, moving `day` back to the last day of the month when that
    month is shorter (e.g. day 31 in April -> 30 April).

    Args:
        year: four-digit year.
        month: month number, 1-12.
        day: desired day of the month, 1-31.

    Returns:
        The date (year, month, min(day, last day of that month)).
    """
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def add_months(year: int, month: int, months: int) -> tuple[int, int]:
    """
    Move a (year, month) pair forward by a number of months, handling the
    year rollover (December + 1 -> January of the next year).

    Args:
        year: starting year.
        month: starting month, 1-12.
        months: how many months to add (0 or more).

    Returns:
        The resulting (year, month) pair.
    """
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def monthly_due_dates(start_date: date, end_date: date) -> list[date]:
    """
    List the dates of a monthly schedule.

    Args:
        start_date: first date of the schedule.
        end_date: last day of the schedule (inclusive).

    Returns:
        The due dates in chronological order: start_date, then the same day of
        every following month (clamped to the month length), up to end_date.
        Empty if end_date < start_date.
    """
    dates = []
    months = 0
    while True:
        year, month = add_months(start_date.year, start_date.month, months)
        due = clamped_date(year, month, start_date.day)
        if due > end_date:
            return dates
        dates.append(due)
        months += 1


def yearly_anniversaries(origin: date, start: date, end: date) -> list[date]:
    """
    List the anniversaries of a date (one, two... years later) in a period.

    A 29 February origin falls on 28 February in the years without it.

    Args:
        origin: the date the anniversaries count from (not an anniversary
            itself).
        start: first day of the period (inclusive).
        end: last day of the period (inclusive).

    Returns:
        The anniversaries in chronological order with start <= date <= end;
        empty if end < start.
    """
    dates = []
    for year in range(max(origin.year + 1, start.year), end.year + 1):
        due = clamped_date(year, origin.month, origin.day)
        if start <= due <= end:
            dates.append(due)
    return dates
