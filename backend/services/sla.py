"""SLA / respond_by helpers for support tickets."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.config import (
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    FIRM_TIMEZONE,
)


def _is_business_day(dt: datetime) -> bool:
    return dt.weekday() < 5  # Mon–Fri


def _at_business_end(dt: datetime, tz: ZoneInfo) -> datetime:
    local = dt.astimezone(tz)
    return local.replace(
        hour=BUSINESS_HOURS_END, minute=0, second=0, microsecond=0
    )


def add_business_hours(start: datetime, hours: int, tz_name: str | None = None) -> datetime:
    """Advance `hours` within Mon–Fri [BUSINESS_HOURS_START, BUSINESS_HOURS_END)."""
    tz = ZoneInfo(tz_name or FIRM_TIMEZONE)
    cur = start.astimezone(tz)
    remaining = hours * 60  # minutes

    # Snap into a business window if outside.
    while True:
        if not _is_business_day(cur):
            cur = (cur + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
            continue
        if cur.hour < BUSINESS_HOURS_START or (
            cur.hour == BUSINESS_HOURS_START and cur.minute < 0
        ):
            cur = cur.replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
        if cur.hour >= BUSINESS_HOURS_END:
            cur = (cur + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
            continue
        break

    while remaining > 0:
        if not _is_business_day(cur) or cur.hour >= BUSINESS_HOURS_END:
            cur = (cur + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
            continue
        end_of_day = cur.replace(
            hour=BUSINESS_HOURS_END, minute=0, second=0, microsecond=0
        )
        available = int((end_of_day - cur).total_seconds() // 60)
        if available <= 0:
            cur = (cur + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
            continue
        step = min(remaining, available)
        cur = cur + timedelta(minutes=step)
        remaining -= step
        if remaining > 0:
            cur = (cur + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
    return cur


def next_business_day_end(start: datetime, tz_name: str | None = None) -> datetime:
    """End of the next business day (or today if still before close and weekday)."""
    tz = ZoneInfo(tz_name or FIRM_TIMEZONE)
    local = start.astimezone(tz)
    # If weekday and before close, respond_by = today at close.
    if _is_business_day(local) and (
        local.hour < BUSINESS_HOURS_END
        or (local.hour == BUSINESS_HOURS_END and local.minute == 0 and local.second == 0)
    ):
        # If already past start of day, use today's close; if before open, still today close.
        if local.hour < BUSINESS_HOURS_END:
            return _at_business_end(local, tz)
    # Move to next calendar day until weekday, then end of that day.
    cur = local + timedelta(days=1)
    while not _is_business_day(cur):
        cur += timedelta(days=1)
    return _at_business_end(cur, tz)


def compute_respond_by(priority: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(ZoneInfo(FIRM_TIMEZONE))
    p = (priority or "normal").lower()
    if p == "high":
        return add_business_hours(now, 4)
    return next_business_day_end(now)


def format_respond_by(dt: datetime, tz_name: str | None = None) -> str:
    tz = ZoneInfo(tz_name or FIRM_TIMEZONE)
    local = dt.astimezone(tz)
    # e.g. Tue, Aug 11, 2026, 5:00 PM PT
    return local.strftime("%a, %b %d, %Y, %I:%M %p %Z").replace(" 0", " ")
